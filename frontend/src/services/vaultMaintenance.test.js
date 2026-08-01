import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiClient, ApiError } from "../lib/client";
import { AuthService } from "./auth";
import { VaultMaintenance } from "./vaultMaintenance";

function cleanupError(code, sessionState, overrides = {}) {
    return new ApiError("cleanup pending", {
        status: 500,
        details: {
            detail: {
                code,
                session_state: sessionState,
                reauth_required: false,
                maintenance_access_token: "rotated-maintenance-token",
                ...overrides,
            },
        },
    });
}

describe("VaultMaintenance", () => {
    beforeEach(() => {
        ApiClient.invalidateSession();
        VaultMaintenance.clearRetryState();
        AuthService._logoutToken = null;
    });

    afterEach(() => vi.restoreAllMocks());

    it.each([
        ["reset_cleanup_pending", "reset_pending"],
        ["restore_cleanup_pending", "restore_pending"],
        ["erasure_cleanup_pending", "erasure_pending"],
    ])("rebinds rotated authority for %s without exposing the token in the event", (code, sessionState) => {
        ApiClient.setToken("previous-token");
        const listener = vi.fn();
        window.addEventListener("careeros:maintenance-pending", listener);

        expect(VaultMaintenance.handleFailure(cleanupError(code, sessionState))).toBe(true);

        expect(ApiClient.getToken()).toBe("rotated-maintenance-token");
        expect(listener).toHaveBeenCalledTimes(1);
        expect(listener.mock.calls[0][0].detail).toEqual({
            sessionState,
            reauthRequired: false,
        });
        expect(JSON.stringify(listener.mock.calls[0][0].detail)).not.toContain("token");
        window.removeEventListener("careeros:maintenance-pending", listener);
    });

    it("clears unusable authority and requires relogin when token rotation fails", () => {
        ApiClient.setToken("stale-token");
        const listener = vi.fn();
        window.addEventListener("careeros:maintenance-pending", listener);

        const error = cleanupError("restore_cleanup_pending", "restore_pending", {
            reauth_required: true,
            maintenance_access_token: undefined,
        });
        expect(VaultMaintenance.handleFailure(error)).toBe(true);

        expect(ApiClient.getToken()).toBeNull();
        expect(listener.mock.calls[0][0].detail).toEqual({
            sessionState: "restore_pending",
            reauthRequired: true,
        });
        window.removeEventListener("careeros:maintenance-pending", listener);
    });

    it("fails closed on an inconsistent cleanup code/state pair", () => {
        ApiClient.setToken("still-current");

        expect(VaultMaintenance.handleFailure(cleanupError(
            "restore_cleanup_pending",
            "reset_pending",
        ))).toBe(false);
        expect(ApiClient.getToken()).toBe("still-current");
    });

    it("retains a restore File only for a validated restore-pending response", () => {
        const archive = new File(["PK"], "private.zip", { type: "application/zip" });

        expect(VaultMaintenance.rememberRestoreArchiveForFailure(
            cleanupError("restore_cleanup_pending", "reset_pending"),
            archive,
        )).toBe(false);
        expect(VaultMaintenance.getRestoreArchive()).toBeNull();

        expect(VaultMaintenance.rememberRestoreArchiveForFailure(
            cleanupError("restore_cleanup_pending", "restore_pending"),
            archive,
        )).toBe(true);
        expect(VaultMaintenance.getRestoreArchive()).toBe(archive);
    });

    it("clears retry memory and ends the renderer session when maintenance access expires", () => {
        const archive = new File(["PK"], "private.zip", { type: "application/zip" });
        VaultMaintenance.rememberRestoreArchive(archive);
        ApiClient.setToken("expired-token");
        const prepareLogout = vi.spyOn(AuthService, "prepareLogout");
        const listener = vi.fn();
        window.addEventListener("careeros:unauthorized", listener);

        expect(VaultMaintenance.handleFailure(new ApiError("expired", { status: 401 }))).toBe(true);

        expect(VaultMaintenance.getRestoreArchive()).toBeNull();
        expect(prepareLogout).toHaveBeenCalledTimes(1);
        expect(ApiClient.getToken()).toBeNull();
        expect(listener.mock.calls[0][0].detail).toEqual({
            messageKey: "auth.maintenanceAccessExpiredSignIn",
        });
        window.removeEventListener("careeros:unauthorized", listener);
    });

    it("captures logout authority, clears retry memory, and broadcasts only a generic completion", () => {
        VaultMaintenance.rememberRestoreArchive(
            new File(["PK"], "private.zip", { type: "application/zip" }),
        );
        ApiClient.setToken("maintenance-token");
        const listener = vi.fn();
        window.addEventListener("careeros:maintenance-complete", listener);

        VaultMaintenance.complete();

        expect(VaultMaintenance.getRestoreArchive()).toBeNull();
        expect(ApiClient.getToken()).toBeNull();
        expect(AuthService._logoutToken).toBe("maintenance-token");
        expect(listener.mock.calls[0][0].detail).toEqual({
            messageKey: "auth.maintenanceCompleteSignIn",
        });
        window.removeEventListener("careeros:maintenance-complete", listener);
    });
});
