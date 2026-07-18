use serde::Serialize;
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

#[cfg(test)]
mod tests {
    use super::DesktopBootstrap;

    #[test]
    fn bootstrap_contract_exposes_only_required_webview_fields() {
        let response = DesktopBootstrap {
            desktop: true,
            api_base_url: "http://127.0.0.1:43127/api/v1".into(),
            session_token: "x".repeat(64),
            app_version: "1.0.0".into(),
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
