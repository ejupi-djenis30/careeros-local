import { ApiClient } from "../lib/client";
import {
    CAREEROS_MAINTENANCE_COMPLETE_EVENT,
    CAREEROS_MAINTENANCE_PENDING_EVENT,
    CAREEROS_UNAUTHORIZED_EVENT,
} from "../lib/events";
import { AuthService } from "./auth";

export const VAULT_MAINTENANCE_STATES = Object.freeze([
    "reset_pending",
    "restore_pending",
    "erasure_pending",
]);

const MAINTENANCE_FAILURE_STATES = Object.freeze({
    reset_cleanup_pending: "reset_pending",
    restore_cleanup_pending: "restore_pending",
    erasure_cleanup_pending: "erasure_pending",
});

let restoreRetryArchive = null;

function pendingDetail(error) {
    const detail = error?.details?.detail;
    if (!detail || typeof detail !== "object" || Array.isArray(detail)) return null;
    const expectedState = MAINTENANCE_FAILURE_STATES[detail.code];
    if (!expectedState || detail.session_state !== expectedState) return null;
    return detail;
}

export const VaultMaintenance = {
    rememberRestoreArchive(file) {
        restoreRetryArchive = file || null;
    },

    rememberRestoreArchiveForFailure(error, file) {
        if (pendingDetail(error)?.session_state !== "restore_pending") return false;
        restoreRetryArchive = file || null;
        return Boolean(restoreRetryArchive);
    },

    getRestoreArchive() {
        return restoreRetryArchive;
    },

    clearRetryState() {
        restoreRetryArchive = null;
    },

    handleFailure(error) {
        const detail = pendingDetail(error);
        if (detail) {
            const maintenanceToken = typeof detail.maintenance_access_token === "string"
                ? detail.maintenance_access_token
                : null;
            const reauthRequired = detail.reauth_required === true || !maintenanceToken;
            ApiClient.bindMaintenanceToken(reauthRequired ? null : maintenanceToken);
            window.dispatchEvent(new CustomEvent(CAREEROS_MAINTENANCE_PENDING_EVENT, {
                detail: {
                    sessionState: detail.session_state,
                    reauthRequired,
                },
            }));
            return true;
        }

        if (error?.status === 401) {
            this.clearRetryState();
            AuthService.prepareLogout();
            window.dispatchEvent(new CustomEvent(CAREEROS_UNAUTHORIZED_EVENT, {
                detail: { messageKey: "auth.maintenanceAccessExpiredSignIn" },
            }));
            return true;
        }

        return false;
    },

    complete() {
        this.clearRetryState();
        AuthService.prepareLogout();
        window.dispatchEvent(new CustomEvent(CAREEROS_MAINTENANCE_COMPLETE_EVENT, {
            detail: { messageKey: "auth.maintenanceCompleteSignIn" },
        }));
    },
};
