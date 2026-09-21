import { getApiBase } from "../../lib/client";

export const READ_ONLY_SCOPES = [
    "system:read",
    "career:read",
    "resume:read",
    "applications:read",
];

export const WORKSPACE_SCOPES = [
    "context:read",
    "proposals:write",
];

export const SCOPES = [
    ...READ_ONLY_SCOPES,
    ...WORKSPACE_SCOPES,
];

export function getCanonicalDesktopUrl(apiBase = getApiBase()) {
    if (apiBase && (apiBase.startsWith("http://") || apiBase.startsWith("https://"))) {
        try {
            const url = new URL(apiBase);
            const host = url.hostname === "localhost" ? "127.0.0.1" : url.hostname;
            const port = url.port ? `:${url.port}` : "";
            return `${url.protocol}//${host}${port}${url.pathname.replace(/\/+$/, "")}`;
        } catch {
            return apiBase;
        }
    }
    if (typeof window !== "undefined" && window.location) {
        const port = window.location.port === "5173" ? "8000" : (window.location.port || "8000");
        return `http://127.0.0.1:${port}/api/v1`;
    }
    return "http://127.0.0.1:8000/api/v1";
}

export function getCodexConfig(desktopUrl = getCanonicalDesktopUrl()) {
    return `[mcp_servers.careeros]
command = "careeros"
args = ["mcp", "serve", "--desktop-url", "${desktopUrl}", "--acknowledge-agent-disclosure"]
env_vars = ["CAREEROS_MCP_TOKEN"]`;
}

export function getClaudeConfig(desktopUrl = getCanonicalDesktopUrl()) {
    return `claude mcp add --scope user careeros -- careeros mcp serve --desktop-url ${desktopUrl} --acknowledge-agent-disclosure`;
}

export const CODEX_CONFIG = getCodexConfig("http://127.0.0.1:8000/api/v1");

export const CLAUDE_CONFIG = getClaudeConfig("http://127.0.0.1:8000/api/v1");

export function errorMessage(error, t, fallbackKey) {
    const code = error?.details?.detail?.code;
    if (code === "authentication_failed") return t("agentAccess.error.password");
    if (code === "grant_not_found") return t("agentAccess.error.notFound");
    if (code === "reauthentication_locked") return t("agentAccess.error.locked");
    if (code === "active_grant_limit") return t("agentAccess.error.activeLimit");
    if (code === "invalid_label") return t("agentAccess.error.invalidLabel");
    if (code === "scope_denied") return t("agentAccess.error.scopeDenied");
    if (code === "grant_expired") return t("agentAccess.error.grantExpired");
    if (code === "grant_revoked") return t("agentAccess.error.grantRevoked");
    return error?.message || t(fallbackKey);
}

export function grantState(grant, now) {
    if (grant.revoked_at) return "revoked";
    const expiry = Date.parse(grant.expires_at);
    if (!Number.isFinite(expiry) || expiry <= now) return "expired";
    return "active";
}
