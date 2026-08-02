export const SCOPES = [
    "system:read",
    "career:read",
    "career:write",
    "resume:read",
    "resume:write",
    "jobs:read",
    "jobs:write",
    "search:execute",
    "providers:read",
    "providers:write",
    "applications:read",
    "applications:write",
];

export const CODEX_CONFIG = `[mcp_servers.careeros]
command = "careeros"
args = ["mcp", "serve", "--acknowledge-agent-disclosure"]
env_vars = ["CAREEROS_MCP_TOKEN"]`;

export const CLAUDE_CONFIG = "claude mcp add --scope user careeros -- careeros mcp serve --acknowledge-agent-disclosure";

export function errorMessage(error, t, fallbackKey) {
    const code = error?.details?.detail?.code;
    if (code === "authentication_failed") return t("agentAccess.error.password");
    if (code === "grant_not_found") return t("agentAccess.error.notFound");
    if (code === "reauthentication_locked") return t("agentAccess.error.locked");
    if (code === "active_grant_limit") return t("agentAccess.error.activeLimit");
    if (code === "invalid_label") return t("agentAccess.error.invalidLabel");
    return error?.message || t(fallbackKey);
}

export function grantState(grant, now) {
    if (grant.revoked_at) return "revoked";
    const expiry = Date.parse(grant.expires_at);
    if (!Number.isFinite(expiry) || expiry <= now) return "expired";
    return "active";
}
