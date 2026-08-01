mod backup;
mod commands;
mod lifecycle;

use std::ffi::OsString;
use std::fs;
use std::path::PathBuf;
use std::sync::Arc;

use tauri::{path::BaseDirectory, Manager, RunEvent};

fn unexpected_smoke_exit_code(smoke_mode: bool, requested_code: Option<i32>) -> Option<i32> {
    (smoke_mode && requested_code.is_none()).then_some(1)
}

fn resolve_data_directory(
    default: PathBuf,
    smoke_mode: bool,
    smoke_override: Option<OsString>,
) -> std::io::Result<PathBuf> {
    if !smoke_mode {
        return Ok(default);
    }
    let value = smoke_override.ok_or_else(|| {
        std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "desktop smoke mode requires CAREEROS_DESKTOP_SMOKE_DATA_DIR",
        )
    })?;
    let path = PathBuf::from(value);
    if !path.is_absolute() || path.parent().is_none() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "desktop smoke data directory must be absolute",
        ));
    }
    Ok(path)
}

#[cfg(windows)]
fn metadata_is_reparse_point(metadata: &fs::Metadata) -> bool {
    use std::os::windows::fs::MetadataExt;

    const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x400;
    metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
}

#[cfg(not(windows))]
fn metadata_is_reparse_point(metadata: &fs::Metadata) -> bool {
    metadata.file_type().is_symlink()
}

fn ensure_regular_directory(path: &std::path::Path) -> std::io::Result<()> {
    match fs::symlink_metadata(path) {
        Ok(metadata) => {
            if !metadata.is_dir() || metadata_is_reparse_point(&metadata) {
                return Err(std::io::Error::other(
                    "desktop data path is not a regular directory",
                ));
            }
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            fs::create_dir_all(path)?;
            let metadata = fs::symlink_metadata(path)?;
            if !metadata.is_dir() || metadata_is_reparse_point(&metadata) {
                return Err(std::io::Error::other(
                    "desktop data path is not a regular directory",
                ));
            }
        }
        Err(error) => return Err(error),
    }
    Ok(())
}

pub fn run() {
    let application = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            backup::desktop_save_verified_backup,
            commands::desktop_bootstrap,
            commands::desktop_frontend_ready
        ])
        .setup(|app| {
            let smoke_mode =
                std::env::var("CAREEROS_DESKTOP_SMOKE").is_ok_and(|value| value == "1");
            let data_directory = resolve_data_directory(
                app.path().app_data_dir()?,
                smoke_mode,
                std::env::var_os("CAREEROS_DESKTOP_SMOKE_DATA_DIR"),
            )?;
            ensure_regular_directory(&data_directory)?;
            ensure_regular_directory(&data_directory.join("staging"))?;
            let port = lifecycle::allocate_loopback_port()?;
            let executable_name = if cfg!(windows) {
                "careeros-backend.exe"
            } else {
                "careeros-backend"
            };
            let executable_path = app.path().resolve(
                format!("careeros-backend-runtime/{executable_name}"),
                BaseDirectory::Resource,
            )?;
            let executable_metadata = std::fs::symlink_metadata(&executable_path)?;
            if executable_metadata.file_type().is_symlink()
                || metadata_is_reparse_point(&executable_metadata)
                || !executable_metadata.is_file()
            {
                return Err(std::io::Error::other(
                    "packaged backend executable is not a regular file",
                )
                .into());
            }
            let state = Arc::new(lifecycle::BackendLifecycle::new(
                port,
                lifecycle::generate_session_token(),
                app.package_info().version.to_string(),
                data_directory,
                executable_path,
                smoke_mode,
            ));
            app.manage(state.clone());
            lifecycle::start_backend_supervisor(app.handle().clone(), state);
            if smoke_mode {
                lifecycle::start_smoke_exit_monitor(app.handle().clone());
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("CareerOS Local desktop runtime failed to build");

    application.run(|app, event| match event {
        RunEvent::ExitRequested { code, api, .. } => {
            let state = app.state::<Arc<lifecycle::BackendLifecycle>>();
            if !state.is_shutdown_complete() {
                let exit_code = unexpected_smoke_exit_code(state.is_smoke_mode(), code)
                    .or(code)
                    .unwrap_or(0);
                api.prevent_exit();
                lifecycle::start_graceful_app_exit(app.clone(), state.inner().clone(), exit_code);
            }
        }
        RunEvent::Exit => app
            .state::<Arc<lifecycle::BackendLifecycle>>()
            .force_shutdown(),
        _ => {}
    });
}

#[cfg(test)]
mod tests {
    use super::{ensure_regular_directory, resolve_data_directory, unexpected_smoke_exit_code};
    use std::ffi::OsString;
    use std::path::PathBuf;

    #[test]
    fn smoke_data_override_must_be_explicit_and_absolute() {
        let default = PathBuf::from("C:/default");
        assert_eq!(
            resolve_data_directory(default.clone(), false, None).unwrap(),
            default
        );
        assert!(resolve_data_directory(default.clone(), true, None).is_err());
        assert!(resolve_data_directory(
            default.clone(),
            true,
            Some(OsString::from("relative/path"))
        )
        .is_err());
        let filesystem_root = PathBuf::from(if cfg!(windows) { "C:/" } else { "/" });
        assert!(resolve_data_directory(
            default.clone(),
            true,
            Some(filesystem_root.into_os_string())
        )
        .is_err());
        let absolute = std::env::temp_dir().join("careeros-smoke");
        assert_eq!(
            resolve_data_directory(default, true, Some(absolute.clone().into_os_string())).unwrap(),
            absolute
        );
    }

    #[test]
    fn desktop_data_directories_must_be_regular() {
        let root = std::env::temp_dir().join(format!(
            "careeros-desktop-directory-{:032x}",
            rand::random::<u128>()
        ));
        let directory = root.join("vault");
        ensure_regular_directory(&directory).unwrap();
        assert!(directory.is_dir());
        let file = root.join("not-a-directory");
        std::fs::write(&file, b"file").unwrap();
        assert!(ensure_regular_directory(&file).is_err());
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn natural_exit_is_a_failure_only_during_packaged_smoke() {
        assert_eq!(unexpected_smoke_exit_code(false, None), None);
        assert_eq!(unexpected_smoke_exit_code(true, None), Some(1));
        assert_eq!(unexpected_smoke_exit_code(true, Some(0)), None);
        assert_eq!(unexpected_smoke_exit_code(true, Some(1)), None);
    }
}
