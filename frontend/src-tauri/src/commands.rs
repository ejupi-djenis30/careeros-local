use serde::Serialize;
use std::path::Path;
use std::sync::Arc;
use tauri::State;

use crate::lifecycle::BackendLifecycle;

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopBootstrap {
    pub desktop: bool,
    pub api_base_url: String,
    pub session_token: String,
    pub app_version: String,
    pub data_directory: String,
    pub backend_state: String,
}

#[tauri::command]
pub fn desktop_bootstrap(state: State<'_, Arc<BackendLifecycle>>) -> DesktopBootstrap {
    state.bootstrap()
}

#[tauri::command]
pub fn desktop_frontend_ready(state: State<'_, Arc<BackendLifecycle>>) -> bool {
    state.mark_frontend_ready()
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopMcpSetup {
    pub command: String,
    pub args: Vec<String>,
    pub connection_file: String,
    pub token_environment_variable: String,
    pub codex_toml: String,
    pub claude_json: String,
}

pub fn mcp_setup_paths(
    executable: &Path,
    data_directory: &Path,
) -> Result<DesktopMcpSetup, String> {
    let directory = executable
        .parent()
        .ok_or("MCP runtime directory is unavailable")?;
    let command = directory.join(if cfg!(windows) {
        "careeros-mcp.exe"
    } else {
        "careeros-mcp"
    });
    let metadata =
        std::fs::symlink_metadata(&command).map_err(|_| "MCP console launcher is unavailable")?;
    if !command.is_absolute()
        || !data_directory.is_absolute()
        || !metadata.is_file()
        || crate::metadata_is_reparse_point(&metadata)
    {
        return Err("MCP console launcher is not a regular installed executable".into());
    }
    let command = command.to_string_lossy().into_owned();
    let connection_file = data_directory
        .join("mcp")
        .join("connection.json")
        .to_string_lossy()
        .into_owned();
    let args = vec![
        "--connection-file".into(),
        connection_file.clone(),
        "--acknowledge-agent-disclosure".into(),
    ];
    let encoded_command =
        serde_json::to_string(&command).map_err(|_| "Cannot encode MCP command")?;
    let encoded_args = serde_json::to_string(&args).map_err(|_| "Cannot encode MCP arguments")?;
    let codex_toml = format!("[mcp_servers.careeros]\ncommand = {encoded_command}\nargs = {encoded_args}\nenv_vars = [\"CAREEROS_MCP_TOKEN\"]\n");
    // Claude inherits CAREEROS_MCP_TOKEN from its launch environment; do not put
    // a secret (or a placeholder that could overwrite the real value) in JSON.
    let claude_json = serde_json::to_string_pretty(
        &serde_json::json!({"mcpServers": {"careeros": {"command": command, "args": args}}}),
    )
    .map_err(|_| "Cannot encode Claude MCP configuration")?;
    Ok(DesktopMcpSetup {
        command,
        args,
        connection_file,
        token_environment_variable: "CAREEROS_MCP_TOKEN".into(),
        codex_toml,
        claude_json,
    })
}

#[tauri::command]
pub fn desktop_mcp_setup(
    state: State<'_, Arc<BackendLifecycle>>,
) -> Result<DesktopMcpSetup, String> {
    state.mcp_setup()
}

#[cfg(test)]
mod tests {
    use super::{mcp_setup_paths, DesktopBootstrap};

    #[test]
    fn installed_mcp_configuration_contains_only_paths_and_token_variable_name() {
        let root = std::env::temp_dir().join(format!("careeros-mcp-{}", rand::random::<u64>()));
        std::fs::create_dir_all(&root).unwrap();
        let console = root.join(if cfg!(windows) {
            "careeros-mcp.exe"
        } else {
            "careeros-mcp"
        });
        std::fs::write(&console, b"synthetic executable").unwrap();
        let data = root.join("vault with spaces");
        let setup = mcp_setup_paths(&root.join("careeros-backend.exe"), &data).unwrap();
        let value = serde_json::to_value(&setup).unwrap();
        assert_eq!(value.as_object().unwrap().len(), 6);
        assert_eq!(setup.command, console.to_string_lossy());
        assert_eq!(
            setup.args,
            vec![
                "--connection-file",
                &setup.connection_file,
                "--acknowledge-agent-disclosure"
            ]
        );
        assert_eq!(setup.token_environment_variable, "CAREEROS_MCP_TOKEN");
        let claude: serde_json::Value = serde_json::from_str(&setup.claude_json).unwrap();
        assert_eq!(claude["mcpServers"]["careeros"]["command"], setup.command);
        assert!(claude["mcpServers"]["careeros"].get("env").is_none());
        assert!(setup
            .codex_toml
            .contains("env_vars = [\"CAREEROS_MCP_TOKEN\"]"));
        assert!(!value.to_string().contains("sessionToken"));
        assert!(!value.to_string().contains("--desktop-url"));
        assert!(!value.to_string().contains("Bearer"));
        std::fs::remove_file(&console).unwrap();
        assert!(mcp_setup_paths(&root.join("careeros-backend.exe"), &data).is_err());
        std::fs::remove_dir(&root).unwrap();
    }

    #[test]
    fn bootstrap_contract_exposes_only_required_webview_fields() {
        let response = DesktopBootstrap {
            desktop: true,
            api_base_url: "http://127.0.0.1:43127/api/v1".into(),
            session_token: "x".repeat(64),
            app_version: env!("CARGO_PKG_VERSION").into(),
            data_directory: "C:/CareerOS".into(),
            backend_state: "waiting_ready".into(),
        };
        let value = serde_json::to_value(response).expect("bootstrap should serialize");
        let object = value.as_object().expect("bootstrap must be an object");
        assert_eq!(object.len(), 6);
        assert!(object.contains_key("apiBaseUrl"));
        assert!(object.contains_key("sessionToken"));
        assert!(!object.contains_key("pid"));
        assert!(!object.contains_key("restartCount"));
        assert!(!object.contains_key("lastError"));
    }
}
