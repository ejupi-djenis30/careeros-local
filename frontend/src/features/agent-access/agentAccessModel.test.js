import { describe, expect, it } from "vitest";

import { errorMessage, grantState } from "./agentAccessModel";

const translate = (key) => key;

describe("agentAccessModel", () => {
    it.each([
        ["authentication_failed", "agentAccess.error.password"],
        ["grant_not_found", "agentAccess.error.notFound"],
        ["reauthentication_locked", "agentAccess.error.locked"],
        ["active_grant_limit", "agentAccess.error.activeLimit"],
        ["invalid_label", "agentAccess.error.invalidLabel"],
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
});
