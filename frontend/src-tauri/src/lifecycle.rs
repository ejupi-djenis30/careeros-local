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
pub const SMOKE_READY_MARKER: &str = ".careeros-desktop-ready-v1";
const SMOKE_READY_PAYLOAD: &str = "backend-ready+frontend-committed\n";

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

    pub fn shutdown(&self) {
        self.shutting_down.store(true, Ordering::Release);
        if let Some(child) = self.child.lock().expect("child state poisoned").take() {
            let _ = child.kill();
        }
    }

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

fn readiness_probe(port: u16, token: &str) -> bool {
    let address = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(300)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
    let request = format!(
        "GET /api/v1/health/ready HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nX-CareerOS-Session: {token}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut response = Vec::with_capacity(1024);
    if stream.read_to_end(&mut response).is_err() {
        return false;
    }
    let response = String::from_utf8_lossy(&response);
    response.starts_with("HTTP/1.1 200") && response.contains("\"status\":\"ready\"")
}

fn start_readiness_monitor(state: Arc<BackendLifecycle>) {
    thread::spawn(move || {
        let deadline = Instant::now() + Duration::from_secs(90);
        while Instant::now() < deadline && !state.shutting_down.load(Ordering::Acquire) {
            if readiness_probe(state.port, &state.session_token) {
                state.set_phase(BackendPhase::Ready);
                return;
            }
            thread::sleep(Duration::from_millis(150));
        }
    });
}

pub fn start_backend_supervisor(app: AppHandle, state: Arc<BackendLifecycle>) {
    tauri::async_runtime::spawn(async move {
        loop {
            if state.shutting_down.load(Ordering::Acquire) {
                break;
            }
            state.set_phase(BackendPhase::Spawning);
            let spawned = app
                .shell()
                .command(&state.executable_path)
                .args(sidecar_arguments(
                    state.port,
                    &state.data_directory,
                    std::process::id(),
                ))
                .env("CAREEROS_DESKTOP_SESSION_TOKEN", &state.session_token)
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
            *state.child.lock().expect("child state poisoned") = Some(child);
            state.set_phase(BackendPhase::WaitingReady);
            start_readiness_monitor(state.clone());

            while let Some(event) = receiver.recv().await {
                if matches!(event, CommandEvent::Terminated(_) | CommandEvent::Error(_)) {
                    break;
                }
            }
            state.child.lock().expect("child state poisoned").take();
            if state.shutting_down.load(Ordering::Acquire) {
                break;
            }
            if !state.can_restart() {
                state.set_phase(BackendPhase::Failed);
                break;
            }
        }
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
        allocate_loopback_port, generate_session_token, sidecar_arguments, smoke_exit_code,
        BackendLifecycle, BackendPhase, RestartPolicy, SMOKE_READY_MARKER,
    };
    use std::path::{Path, PathBuf};

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
    fn restart_policy_is_strictly_bounded() {
        let mut policy = RestartPolicy::bounded(2);
        assert!(policy.register_failure());
        assert!(policy.register_failure());
        assert!(!policy.register_failure());
        assert!(!policy.register_failure());
    }

    #[test]
    fn frontend_readiness_is_smoke_only_and_idempotent() {
        let lifecycle = |smoke_mode| {
            BackendLifecycle::new(
                43127,
                "x".repeat(64),
                "1.1.2".into(),
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
            "1.1.2".into(),
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
