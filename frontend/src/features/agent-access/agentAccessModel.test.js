import { describe, expect, it } from "vitest";

import {
    CLAUDE_CONFIG,
    CODEX_CONFIG,
    errorMessage,
    getCanonicalDesktopUrl,
    getClaudeConfig,
    getCodexConfig,
    grantState,
    READ_ONLY_SCOPES,
    SCOPES,
    WORKSPACE_SCOPES,
} from "./agentAccessModel";

const translate = (key) => key;

describe("agentAccessModel", () => {
    it.each([
        ["authentication_failed", "agentAccess.error.password"],
        ["grant_not_found", "agentAccess.error.notFound"],
        ["reauthentication_locked", "agentAccess.error.locked"],
        ["active_grant_limit", "agentAccess.error.activeLimit"],
        ["invalid_label", "agentAccess.error.invalidLabel"],
        ["scope_denied", "agentAccess.error.scopeDenied"],
        ["grant_expired", "agentAccess.error.grantExpired"],
        ["grant_revoked", "agentAccess.error.grantRevoked"],
    ])("maps the stable %s error without exposing backend copy", (code, expected) => {
        const error = {
            message: "backend detail",
            details: { detail: { code, message: "backend detail" } },
        };

        expect(errorMessage(error, translate, "fallback")).toBe(expected);
    });

    it("derives grant lifecycle without trusting a server-provided status", () => {
        const now = Date.parse("2026-07-30T00:00:00Z");

        expect(grantState({ expires_at: "2030-01-01T00:00:00Z", revoked_at: null }, now))
            .toBe("active");
        expect(grantState({ expires_at: "2020-01-01T00:00:00Z", revoked_at: null }, now))
            .toBe("expired");
        expect(grantState({
            expires_at: "2030-01-01T00:00:00Z",
            revoked_at: "2026-07-29T00:00:00Z",
        }, now)).toBe("revoked");
    });

    it("defines scopes with separate explicit workspace opt-ins", () => {
        expect(READ_ONLY_SCOPES).toEqual([
            "system:read",
            "career:read",
            "resume:read",
            "applications:read",
        ]);
        expect(WORKSPACE_SCOPES).toEqual([
            "context:read",
            "proposals:write",
        ]);
        expect(SCOPES).toEqual([...READ_ONLY_SCOPES, ...WORKSPACE_SCOPES]);
    });

    it("derives canonical loopback URL correctly", () => {
        expect(getCanonicalDesktopUrl("http://localhost:8000/api/v1"))
            .toBe("http://127.0.0.1:8000/api/v1");
        expect(getCanonicalDesktopUrl("http://127.0.0.1:8000/api/v1/"))
            .toBe("http://127.0.0.1:8000/api/v1");
    });

    it("generates token-free Codex and Claude configurations with desktop-url and disclosure flag", () => {
        const testUrl = "http://127.0.0.1:8000/api/v1";
        const codex = getCodexConfig(testUrl);
        const claude = getClaudeConfig(testUrl);

        expect(codex).toContain("--desktop-url");
        expect(codex).toContain(testUrl);
        expect(codex).toContain("--acknowledge-agent-disclosure");
        expect(codex).toContain("CAREEROS_MCP_TOKEN");
        expect(codex).not.toContain("careeros_mcp_v1_");
        expect(codex).not.toContain("Bearer");

        expect(claude).toContain("--desktop-url");
        expect(claude).toContain(testUrl);
        expect(claude).toContain("--acknowledge-agent-disclosure");
        expect(claude).not.toContain("CAREEROS_MCP_TOKEN");
        expect(claude).not.toContain("Bearer");
    });

    it("exports compatible static configurations", () => {
        expect(CODEX_CONFIG).toContain("--desktop-url");
        expect(CODEX_CONFIG).toContain("--acknowledge-agent-disclosure");
        expect(CLAUDE_CONFIG).toContain("--desktop-url");
        expect(CLAUDE_CONFIG).toContain("--acknowledge-agent-disclosure");
    });
});
