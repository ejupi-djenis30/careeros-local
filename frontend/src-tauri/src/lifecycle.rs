use std::ffi::OsString;
use std::fs::OpenOptions;
use std::io::{Read, Write};
use std::net::{Ipv4Addr, SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

use crate::commands::DesktopBootstrap;

const MAX_RESTARTS: u8 = 2;
const GRACEFUL_SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(30);
const FORCED_SHUTDOWN_SETTLE_TIMEOUT: Duration = Duration::from_secs(2);
const SHUTDOWN_POLL_INTERVAL: Duration = Duration::from_millis(100);
const BACKEND_READINESS_TIMEOUT: Duration = Duration::from_secs(90);
const READINESS_PROBE_TOTAL_TIMEOUT: Duration = Duration::from_secs(1);
const READINESS_RESPONSE_MAX_BYTES: usize = 8 * 1024;
pub const SMOKE_READY_MARKER: &str = ".careeros-desktop-ready-v1";
const SMOKE_READY_PAYLOAD: &str = "backend-ready+frontend-committed\n";
const SIDECAR_ENVIRONMENT_NAMES: &[&str] = &[
    "APPDATA",
    "COMSPEC",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOCALAPPDATA",
    "NUMBER_OF_PROCESSORS",
    "PATH",
    "PATHEXT",
    "PROCESSOR_ARCHITECTURE",
    "PROGRAMDATA",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "TZ",
    "USERPROFILE",
    "WINDIR",
];
const SIDECAR_ACCELERATOR_ENVIRONMENT_NAMES: &[&str] = &[
    "CUDA_CACHE_PATH",
    "CUDA_DEVICE_ORDER",
    "CUDA_MODULE_LOADING",
    "CUDA_PATH",
    "CUDA_VISIBLE_DEVICES",
    "HIP_PATH",
    "HIP_VISIBLE_DEVICES",
    "HSA_OVERRIDE_GFX_VERSION",
    "NVIDIA_DRIVER_CAPABILITIES",
    "NVIDIA_VISIBLE_DEVICES",
    "ONEAPI_ROOT",
    "ROCM_PATH",
    "ROCR_VISIBLE_DEVICES",
    "VK_ICD_FILENAMES",
    "VK_LAYER_PATH",
    "VULKAN_SDK",
];

#[cfg(windows)]
struct ProcessJob {
    handle: usize,
}

#[cfg(windows)]
impl Drop for ProcessJob {
    fn drop(&mut self) {
        use windows_sys::Win32::Foundation::CloseHandle;

        // SAFETY: `handle` is created by `CreateJobObjectW`, remains owned by
        // this value, and is closed exactly once here.
        unsafe {
            CloseHandle(self.handle as _);
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BackendPhase {
    Spawning,
    WaitingReady,
    Ready,
    Failed,
}

impl BackendPhase {
    fn as_contract_value(self) -> &'static str {
        match self {
            Self::Spawning => "spawning",
            Self::WaitingReady => "waiting_ready",
            Self::Ready => "ready",
            Self::Failed => "failed",
        }
    }
}

#[derive(Clone, Debug)]
struct LifecycleSnapshot {
    phase: BackendPhase,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RestartPolicy {
    attempts: u8,
    maximum: u8,
}

impl RestartPolicy {
    pub fn bounded(maximum: u8) -> Self {
        Self {
            attempts: 0,
            maximum,
        }
    }

    pub fn register_failure(&mut self) -> bool {
        if self.attempts >= self.maximum {
            return false;
        }
        self.attempts += 1;
        true
    }
}

pub struct BackendLifecycle {
    port: u16,
    session_token: String,
    app_version: String,
    data_directory: PathBuf,
    executable_path: PathBuf,
    snapshot: Mutex<LifecycleSnapshot>,
    child: Mutex<Option<CommandChild>>,
    restart_policy: Mutex<RestartPolicy>,
    shutting_down: AtomicBool,
    supervisor_running: AtomicBool,
    shutdown_complete: AtomicBool,
    #[cfg(windows)]
    process_job: Mutex<Option<ProcessJob>>,
    smoke_mode: bool,
    frontend_ready: AtomicBool,
}

impl BackendLifecycle {
    pub fn new(
        port: u16,
        session_token: String,
        app_version: String,
        data_directory: PathBuf,
        executable_path: PathBuf,
        smoke_mode: bool,
    ) -> Self {
        Self {
            port,
            session_token,
            app_version,
            data_directory,
            executable_path,
            snapshot: Mutex::new(LifecycleSnapshot {
                phase: BackendPhase::Spawning,
            }),
            child: Mutex::new(None),
            restart_policy: Mutex::new(RestartPolicy::bounded(MAX_RESTARTS)),
            shutting_down: AtomicBool::new(false),
            supervisor_running: AtomicBool::new(false),
            shutdown_complete: AtomicBool::new(false),
            #[cfg(windows)]
            process_job: Mutex::new(None),
            smoke_mode,
            frontend_ready: AtomicBool::new(false),
        }
    }

    pub fn bootstrap(&self) -> DesktopBootstrap {
        let phase = self
            .snapshot
            .lock()
            .expect("lifecycle snapshot poisoned")
            .phase;
        DesktopBootstrap {
            desktop: true,
            api_base_url: format!("http://127.0.0.1:{}/api/v1", self.port),
            session_token: self.session_token.clone(),
            app_version: self.app_version.clone(),
            data_directory: self.data_directory.to_string_lossy().into_owned(),
            backend_state: phase.as_contract_value().into(),
        }
    }

    fn set_phase(&self, phase: BackendPhase) {
        self.snapshot
            .lock()
            .expect("lifecycle snapshot poisoned")
            .phase = phase;
    }

    fn can_restart(&self) -> bool {
        self.restart_policy
            .lock()
            .expect("restart policy poisoned")
            .register_failure()
    }

    fn begin_shutdown(&self) -> bool {
        !self.shutting_down.swap(true, Ordering::AcqRel)
    }

    pub fn is_shutdown_complete(&self) -> bool {
        self.shutdown_complete.load(Ordering::Acquire)
    }

    fn mark_shutdown_complete(&self) {
        self.shutdown_complete.store(true, Ordering::Release);
    }

    fn child_running(&self) -> bool {
        self.child.lock().expect("child state poisoned").is_some()
    }

    fn supervisor_running(&self) -> bool {
        self.supervisor_running.load(Ordering::Acquire)
    }

    pub fn force_shutdown(&self) {
        self.shutting_down.store(true, Ordering::Release);
        let child = self.child.lock().expect("child state poisoned").take();
        self.release_process_job();
        if let Some(child) = child {
            let _ = child.kill();
        }
    }

    #[cfg(windows)]
    fn assign_process_job(&self, process_id: u32) -> std::io::Result<()> {
        use std::mem::size_of;
        use std::ptr;

        use windows_sys::Win32::Foundation::{CloseHandle, GetLastError};
        use windows_sys::Win32::System::JobObjects::{
            AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
            SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        };
        use windows_sys::Win32::System::Threading::{
            OpenProcess, PROCESS_SET_QUOTA, PROCESS_TERMINATE,
        };

        let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

        // SAFETY: all pointers are either null (for optional arguments) or
        // refer to initialized values for the documented duration of the call.
        let job = unsafe { CreateJobObjectW(ptr::null(), ptr::null()) };
        if job.is_null() {
            return Err(std::io::Error::last_os_error());
        }
        // SAFETY: `job` is a valid owned handle and `limits` has the exact
        // layout required by `JobObjectExtendedLimitInformation`.
        let configured = unsafe {
            SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                (&raw const limits).cast(),
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            )
        };
        if configured == 0 {
            let error = std::io::Error::last_os_error();
            // SAFETY: `job` is still owned locally and has not been closed.
            unsafe { CloseHandle(job) };
            return Err(error);
        }

        // SAFETY: access rights are the documented minimum for assigning an
        // existing process to a job; the process id comes from the spawned child.
        let process = unsafe { OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, 0, process_id) };
        if process.is_null() {
            let error = std::io::Error::last_os_error();
            // SAFETY: `job` is still owned locally and has not been closed.
            unsafe { CloseHandle(job) };
            return Err(error);
        }
        // SAFETY: both handles are valid for the duration of this call.
        let assigned = unsafe { AssignProcessToJobObject(job, process) };
        let assignment_error = if assigned == 0 {
            // SAFETY: read the thread-local Win32 error before any other FFI call can overwrite it.
            Some(unsafe { GetLastError() })
        } else {
            None
        };
        // SAFETY: the temporary process handle is no longer needed after the
        // assignment attempt and remains owned locally.
        unsafe { CloseHandle(process) };
        if let Some(error) = assignment_error {
            // SAFETY: `job` is still owned locally and has not been closed.
            unsafe { CloseHandle(job) };
            return Err(std::io::Error::from_raw_os_error(error as i32));
        }

        let previous = self
            .process_job
            .lock()
            .expect("process job state poisoned")
            .replace(ProcessJob {
                handle: job as usize,
            });
        drop(previous);
        Ok(())
    }

    #[cfg(not(windows))]
    fn assign_process_job(&self, _process_id: u32) -> std::io::Result<()> {
        Ok(())
    }

    #[cfg(windows)]
    fn release_process_job(&self) {
        self.process_job
            .lock()
            .expect("process job state poisoned")
            .take();
    }

    #[cfg(not(windows))]
    fn release_process_job(&self) {}

    pub fn mark_frontend_ready(&self) -> bool {
        if !self.smoke_mode {
            return false;
        }
        self.frontend_ready.store(true, Ordering::Release);
        true
    }

    fn is_frontend_ready(&self) -> bool {
        self.frontend_ready.load(Ordering::Acquire)
    }

    pub fn is_smoke_mode(&self) -> bool {
        self.smoke_mode
    }

    fn write_smoke_readiness_evidence(&self) -> std::io::Result<()> {
        let phase = self
            .snapshot
            .lock()
            .expect("lifecycle snapshot poisoned")
            .phase;
        if !self.smoke_mode || phase != BackendPhase::Ready || !self.is_frontend_ready() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::PermissionDenied,
                "desktop smoke readiness is incomplete",
            ));
        }

        let marker = self.data_directory.join(SMOKE_READY_MARKER);
        let mut evidence = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(marker)?;
        evidence.write_all(SMOKE_READY_PAYLOAD.as_bytes())?;
        evidence.sync_all()
    }
}

pub fn allocate_loopback_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0))?;
    Ok(listener.local_addr()?.port())
}

pub fn generate_session_token() -> String {
    let random: [u8; 32] = rand::random();
    random.iter().map(|byte| format!("{byte:02x}")).collect()
}

pub fn sidecar_arguments(port: u16, data_directory: &Path, parent_pid: u32) -> Vec<String> {
    vec![
        "--host".into(),
        "127.0.0.1".into(),
        "--port".into(),
        port.to_string(),
        "--data-dir".into(),
        data_directory.to_string_lossy().into_owned(),
        "--parent-pid".into(),
        parent_pid.to_string(),
    ]
}

fn sidecar_environment_name_allowed(name: &str, smoke_mode: bool) -> bool {
    let canonical = name.to_ascii_uppercase();
    SIDECAR_ENVIRONMENT_NAMES.contains(&canonical.as_str())
        || SIDECAR_ACCELERATOR_ENVIRONMENT_NAMES.contains(&canonical.as_str())
        || (smoke_mode && canonical == "OFFLINE_MODE")
}

fn sidecar_environment(smoke_mode: bool) -> Vec<(OsString, OsString)> {
    std::env::vars_os()
        .filter(|(name, _)| {
            let Some(name) = name.to_str() else {
                return false;
            };
            sidecar_environment_name_allowed(name, smoke_mode)
        })
        .collect()
}

fn sidecar_working_directory(executable_path: &Path) -> std::io::Result<&Path> {
    executable_path
        .parent()
        .filter(|path| path.is_dir())
        .ok_or_else(|| {
            std::io::Error::new(
                std::io::ErrorKind::NotFound,
                "packaged backend runtime directory is missing",
            )
        })
}

fn readiness_response_is_ready(response: &[u8]) -> bool {
    if response.len() > READINESS_RESPONSE_MAX_BYTES {
        return false;
    }
    let Some(header_end) = response.windows(4).position(|window| window == b"\r\n\r\n") else {
        return false;
    };
    let Ok(headers) = std::str::from_utf8(&response[..header_end]) else {
        return false;
    };
    let mut lines = headers.split("\r\n");
    if lines.next() != Some("HTTP/1.1 200 OK") {
        return false;
    }
    let mut content_type: Option<&str> = None;
    let mut content_length: Option<usize> = None;
    for line in lines {
        let Some((name, value)) = line.split_once(':') else {
            return false;
        };
        match name.trim().to_ascii_lowercase().as_str() {
            "content-type" => {
                if content_type.replace(value.trim()).is_some() {
                    return false;
                }
            }
            "content-length" => {
                let Ok(length) = value.trim().parse::<usize>() else {
                    return false;
                };
                if content_length.replace(length).is_some() {
                    return false;
                }
            }
            "transfer-encoding" => return false,
            _ => {}
        }
    }
    let body = &response[header_end + 4..];
    if content_length != Some(body.len())
        || !content_type.is_some_and(|value| {
            value.split(';').next().is_some_and(|media_type| {
                media_type.trim().eq_ignore_ascii_case("application/json")
            })
        })
    {
        return false;
    }
    serde_json::from_slice::<serde_json::Value>(body)
        .ok()
        .and_then(|value| {
            value
                .get("status")
                .and_then(serde_json::Value::as_str)
                .map(str::to_owned)
        })
        .is_some_and(|status| status == "ready")
}

fn readiness_probe(port: u16, token: &str) -> bool {
    let address = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(300)) else {
        return false;
    };
    let _ = stream.set_write_timeout(Some(Duration::from_millis(300)));
    let request = format!(
        "GET /api/v1/health/ready HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nX-CareerOS-Session: {token}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let deadline = Instant::now() + READINESS_PROBE_TOTAL_TIMEOUT;
    let mut response = Vec::with_capacity(1024);
    let mut chunk = [0_u8; 1024];
    loop {
        let Some(remaining) = deadline.checked_duration_since(Instant::now()) else {
            return false;
        };
        if stream
            .set_read_timeout(Some(remaining.min(Duration::from_millis(250))))
            .is_err()
        {
            return false;
        }
        let count = match stream.read(&mut chunk) {
            Ok(0) => break,
            Ok(count) => count,
            Err(_) => return false,
        };
        if response.len().saturating_add(count) > READINESS_RESPONSE_MAX_BYTES {
            return false;
        }
        response.extend_from_slice(&chunk[..count]);
    }
    readiness_response_is_ready(&response)
}

fn request_backend_shutdown(port: u16, token: &str) -> bool {
    let address = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(300)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));
    let request = format!(
        "POST /api/v1/desktop/shutdown HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nX-CareerOS-Session: {token}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut response = [0_u8; 256];
    let Ok(length) = stream.read(&mut response) else {
        return false;
    };
    response[..length].starts_with(b"HTTP/1.1 202")
}

pub fn start_graceful_app_exit(app: AppHandle, state: Arc<BackendLifecycle>, exit_code: i32) {
    if !state.begin_shutdown() {
        return;
    }

    thread::spawn(move || {
        let deadline = Instant::now() + GRACEFUL_SHUTDOWN_TIMEOUT;
        let mut shutdown_requested = false;
        while Instant::now() < deadline {
            if !state.child_running() && !state.supervisor_running() {
                state.mark_shutdown_complete();
                app.exit(exit_code);
                return;
            }
            if state.child_running() && !shutdown_requested {
                shutdown_requested = request_backend_shutdown(state.port, &state.session_token);
            }
            thread::sleep(SHUTDOWN_POLL_INTERVAL);
        }

        // The authenticated endpoint or Uvicorn drain did not complete within
        // the hard bound. Closing the Windows job also terminates descendants.
        state.force_shutdown();
        let settle_deadline = Instant::now() + FORCED_SHUTDOWN_SETTLE_TIMEOUT;
        while state.supervisor_running() && Instant::now() < settle_deadline {
            thread::sleep(SHUTDOWN_POLL_INTERVAL);
        }
        state.mark_shutdown_complete();
        app.exit(exit_code);
    });
}

fn start_readiness_monitor(state: Arc<BackendLifecycle>, process_id: u32) {
    thread::spawn(move || {
        let deadline = Instant::now() + BACKEND_READINESS_TIMEOUT;
        while Instant::now() < deadline && !state.shutting_down.load(Ordering::Acquire) {
            if readiness_probe(state.port, &state.session_token) {
                state.set_phase(BackendPhase::Ready);
                return;
            }
            thread::sleep(Duration::from_millis(150));
        }
        if state.shutting_down.load(Ordering::Acquire) {
            return;
        }
        let phase = state
            .snapshot
            .lock()
            .expect("lifecycle snapshot poisoned")
            .phase;
        if phase == BackendPhase::Ready {
            return;
        }
        let child = {
            let mut child_state = state.child.lock().expect("child state poisoned");
            if child_state
                .as_ref()
                .is_some_and(|child| child.pid() == process_id)
            {
                child_state.take()
            } else {
                None
            }
        };
        if let Some(child) = child {
            state.set_phase(BackendPhase::Failed);
            state.release_process_job();
            let _ = child.kill();
        }
    });
}

pub fn start_backend_supervisor(app: AppHandle, state: Arc<BackendLifecycle>) {
    state.supervisor_running.store(true, Ordering::Release);
    tauri::async_runtime::spawn(async move {
        loop {
            if state.shutting_down.load(Ordering::Acquire) {
                break;
            }
            state.set_phase(BackendPhase::Spawning);
            let working_directory = match sidecar_working_directory(&state.executable_path) {
                Ok(value) => value,
                Err(_) => {
                    state.set_phase(BackendPhase::Failed);
                    break;
                }
            };
            let spawned = app
                .shell()
                .command(&state.executable_path)
                .env_clear()
                .envs(sidecar_environment(state.smoke_mode))
                .args(sidecar_arguments(
                    state.port,
                    &state.data_directory,
                    std::process::id(),
                ))
                .env("CAREEROS_DESKTOP_SESSION_TOKEN", &state.session_token)
                .current_dir(working_directory)
                .spawn();
            let (mut receiver, child) = match spawned {
                Ok(value) => value,
                Err(_) => {
                    if state.can_restart() {
                        continue;
                    }
                    state.set_phase(BackendPhase::Failed);
                    break;
                }
            };
            let process_id = child.pid();
            if state.assign_process_job(process_id).is_err() {
                let _ = child.kill();
                state.release_process_job();
                state.set_phase(BackendPhase::Failed);
                break;
            }
            {
                let mut child_state = state.child.lock().expect("child state poisoned");
                if state.shutting_down.load(Ordering::Acquire) {
                    drop(child_state);
                    state.release_process_job();
                    let _ = child.kill();
                    break;
                }
                *child_state = Some(child);
            }
            state.set_phase(BackendPhase::WaitingReady);
            start_readiness_monitor(state.clone(), process_id);

            let mut terminated = false;
            while let Some(event) = receiver.recv().await {
                match event {
                    CommandEvent::Terminated(_) => {
                        terminated = true;
                        break;
                    }
                    CommandEvent::Error(_) => break,
                    _ => {}
                }
            }
            let child = state.child.lock().expect("child state poisoned").take();
            state.release_process_job();
            if !terminated {
                if let Some(child) = child {
                    let _ = child.kill();
                }
            }
            if state.shutting_down.load(Ordering::Acquire) {
                break;
            }
            if !state.can_restart() {
                state.set_phase(BackendPhase::Failed);
                break;
            }
        }
        state.supervisor_running.store(false, Ordering::Release);
    });
}

fn smoke_exit_code(phase: BackendPhase, frontend_ready: bool) -> Option<i32> {
    match (phase, frontend_ready) {
        (BackendPhase::Ready, true) => Some(0),
        (BackendPhase::Failed, _) => Some(1),
        (BackendPhase::Spawning | BackendPhase::WaitingReady | BackendPhase::Ready, _) => None,
    }
}

pub fn start_smoke_exit_monitor(app: AppHandle) {
    thread::spawn(move || {
        let deadline = Instant::now() + Duration::from_secs(90);
        while Instant::now() < deadline {
            let state = app.state::<Arc<BackendLifecycle>>();
            let phase = state
                .snapshot
                .lock()
                .expect("lifecycle snapshot poisoned")
                .phase;
            if let Some(code) = smoke_exit_code(phase, state.is_frontend_ready()) {
                if code == 0 && state.write_smoke_readiness_evidence().is_err() {
                    app.exit(1);
                    return;
                }
                app.exit(code);
                return;
            }
            thread::sleep(Duration::from_millis(100));
        }
        app.exit(1);
    });
}

#[cfg(test)]
mod tests {
    use super::{
        allocate_loopback_port, generate_session_token, readiness_probe,
        readiness_response_is_ready, request_backend_shutdown, sidecar_arguments,
        sidecar_environment_name_allowed, smoke_exit_code, BackendLifecycle, BackendPhase,
        RestartPolicy, SMOKE_READY_MARKER,
    };
    use std::io::{Read, Write};
    use std::net::{Ipv4Addr, TcpListener};
    use std::path::{Path, PathBuf};
    use std::thread;
    use std::time::{Duration, Instant};

    #[test]
    fn allocates_an_ephemeral_ipv4_loopback_port() {
        let port = allocate_loopback_port().expect("a loopback port should be available");
        assert!(port > 0);
    }

    #[test]
    fn session_token_has_contract_safe_entropy() {
        let first = generate_session_token();
        let second = generate_session_token();
        assert_eq!(first.len(), 64);
        assert!(first.chars().all(|character| character.is_ascii_hexdigit()));
        assert_ne!(first, second);
    }

    #[test]
    fn sidecar_arguments_never_include_the_session_secret() {
        let arguments = sidecar_arguments(43127, Path::new("C:/CareerOS Data"), 4242);
        assert_eq!(
            arguments,
            [
                "--host",
                "127.0.0.1",
                "--port",
                "43127",
                "--data-dir",
                "C:/CareerOS Data",
                "--parent-pid",
                "4242"
            ]
        );
        assert!(!arguments.iter().any(|value| value.contains("token")));
    }

    #[test]
    fn sidecar_environment_is_an_explicit_non_secret_allowlist() {
        for name in [
            "AWS_SECRET_ACCESS_KEY",
            "CAREEROS_DESKTOP_SESSION_TOKEN",
            "DATABASE_URL",
            "GITHUB_TOKEN",
            "CUDA_API_KEY",
            "INTEL_SECRET",
            "LD_PRELOAD",
            "NVIDIA_API_KEY",
            "PYTHONPATH",
            "SECRET_KEY",
            "SSLKEYLOGFILE",
        ] {
            assert!(!sidecar_environment_name_allowed(name, false), "{name}");
        }
        for name in ["PATH", "SystemRoot", "TEMP", "CUDA_VISIBLE_DEVICES"] {
            assert!(sidecar_environment_name_allowed(name, false), "{name}");
        }
        assert!(!sidecar_environment_name_allowed("OFFLINE_MODE", false));
        assert!(sidecar_environment_name_allowed("OFFLINE_MODE", true));
    }

    #[test]
    fn restart_policy_is_strictly_bounded() {
        let mut policy = RestartPolicy::bounded(2);
        assert!(policy.register_failure());
        assert!(policy.register_failure());
        assert!(!policy.register_failure());
        assert!(!policy.register_failure());
    }

    #[test]
    fn shutdown_request_is_loopback_token_authenticated() {
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut request = Vec::new();
            let mut chunk = [0_u8; 256];
            while !request.windows(4).any(|window| window == b"\r\n\r\n") {
                let count = stream.read(&mut chunk).unwrap();
                if count == 0 {
                    break;
                }
                request.extend_from_slice(&chunk[..count]);
            }
            stream
                .write_all(
                    b"HTTP/1.1 202 Accepted\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
                )
                .unwrap();
            String::from_utf8(request).unwrap()
        });

        assert!(request_backend_shutdown(port, "desktop-secret"));
        let request = server.join().unwrap();
        assert!(request.starts_with("POST /api/v1/desktop/shutdown HTTP/1.1\r\n"));
        assert!(request.contains("\r\nX-CareerOS-Session: desktop-secret\r\n"));
        assert!(request.contains("\r\nContent-Length: 0\r\n"));
    }

    #[test]
    fn readiness_requires_an_exact_bounded_json_response_body() {
        let ready_body = br#"{"status":"ready"}"#;
        let ready = format!(
            "HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: {}\r\n\r\n",
            ready_body.len()
        )
        .into_bytes();
        let mut response = ready;
        response.extend_from_slice(ready_body);
        assert!(readiness_response_is_ready(&response));

        let false_body = br#"{"status":"starting"}"#;
        let false_header = format!(
            "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nX-Fake: \\\"status\\\":\\\"ready\\\"\r\nContent-Length: {}\r\n\r\n",
            false_body.len()
        );
        let mut false_response = false_header.into_bytes();
        false_response.extend_from_slice(false_body);
        assert!(!readiness_response_is_ready(&false_response));
        assert!(!readiness_response_is_ready(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 18\r\n\r\n{\"status\":\"ready\"}"
        ));
    }

    #[test]
    fn readiness_probe_rejects_an_oversized_loopback_response() {
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut request = [0_u8; 1024];
            let _ = stream.read(&mut request);
            let body = vec![b'x'; 9 * 1024];
            let header = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n",
                body.len()
            );
            let _ = stream.write_all(header.as_bytes());
            let _ = stream.write_all(&body);
        });

        assert!(!readiness_probe(port, "desktop-secret"));
        server.join().unwrap();
    }

    #[test]
    fn readiness_probe_has_a_total_deadline_against_slow_drip_responses() {
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut request = [0_u8; 1024];
            let _ = stream.read(&mut request);
            let header =
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 18\r\n\r\n";
            if stream.write_all(header).is_err() {
                return;
            }
            for byte in br#"{"status":"ready"}"# {
                if stream.write_all(&[*byte]).is_err() {
                    break;
                }
                thread::sleep(Duration::from_millis(150));
            }
        });

        let started = Instant::now();
        assert!(!readiness_probe(port, "desktop-secret"));
        assert!(started.elapsed() < Duration::from_secs(2));
        server.join().unwrap();
    }

    #[test]
    fn shutdown_state_is_idempotent_and_explicitly_completed() {
        let lifecycle = BackendLifecycle::new(
            43127,
            "x".repeat(64),
            "1.3.0".into(),
            PathBuf::from("C:/CareerOS"),
            PathBuf::from("C:/CareerOS/careeros-backend.exe"),
            false,
        );

        assert!(lifecycle.begin_shutdown());
        assert!(!lifecycle.begin_shutdown());
        assert!(!lifecycle.is_shutdown_complete());
        lifecycle.mark_shutdown_complete();
        assert!(lifecycle.is_shutdown_complete());
    }

    #[test]
    fn frontend_readiness_is_smoke_only_and_idempotent() {
        let lifecycle = |smoke_mode| {
            BackendLifecycle::new(
                43127,
                "x".repeat(64),
                "1.3.0".into(),
                PathBuf::from("C:/CareerOS"),
                PathBuf::from("C:/CareerOS/careeros-backend.exe"),
                smoke_mode,
            )
        };

        let production = lifecycle(false);
        assert!(!production.mark_frontend_ready());
        assert!(!production.is_frontend_ready());

        let smoke = lifecycle(true);
        assert!(smoke.mark_frontend_ready());
        assert!(smoke.mark_frontend_ready());
        assert!(smoke.is_frontend_ready());
    }

    #[test]
    fn smoke_success_requires_both_backend_and_committed_frontend() {
        assert_eq!(smoke_exit_code(BackendPhase::Spawning, false), None);
        assert_eq!(smoke_exit_code(BackendPhase::WaitingReady, true), None);
        assert_eq!(smoke_exit_code(BackendPhase::Ready, false), None);
        assert_eq!(smoke_exit_code(BackendPhase::Ready, true), Some(0));
        assert_eq!(smoke_exit_code(BackendPhase::Failed, true), Some(1));
    }

    #[test]
    fn smoke_success_writes_fresh_external_evidence() {
        let data_directory = std::env::temp_dir().join(format!(
            "careeros-smoke-evidence-{}",
            generate_session_token()
        ));
        std::fs::create_dir_all(&data_directory).unwrap();
        let lifecycle = BackendLifecycle::new(
            43127,
            "x".repeat(64),
            "1.3.0".into(),
            data_directory.clone(),
            data_directory.join("careeros-backend.exe"),
            true,
        );
        lifecycle.set_phase(BackendPhase::Ready);
        assert!(lifecycle.mark_frontend_ready());
        lifecycle.write_smoke_readiness_evidence().unwrap();

        let marker = data_directory.join(SMOKE_READY_MARKER);
        assert_eq!(
            std::fs::read_to_string(&marker).unwrap(),
            "backend-ready+frontend-committed\n"
        );
        assert!(lifecycle.write_smoke_readiness_evidence().is_err());
        std::fs::remove_dir_all(data_directory).unwrap();
    }
}
