mod commands;
mod lifecycle;

use std::sync::Arc;

use tauri::{path::BaseDirectory, Manager, RunEvent};

pub fn run() {
    let application = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![commands::desktop_bootstrap])
        .setup(|app| {
            let data_directory = app.path().app_data_dir()?;
            std::fs::create_dir_all(&data_directory)?;
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
            let state = Arc::new(lifecycle::BackendLifecycle::new(
                port,
                lifecycle::generate_session_token(),
                app.package_info().version.to_string(),
                data_directory,
                executable_path,
            ));
            app.manage(state.clone());
            lifecycle::start_backend_supervisor(app.handle().clone(), state);
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("CareerOS Local desktop runtime failed to build");

    application.run(|app, event| {
        if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
            app.state::<Arc<lifecycle::BackendLifecycle>>().shutdown();
        }
    });
}
