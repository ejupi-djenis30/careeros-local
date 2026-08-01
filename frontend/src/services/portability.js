import { ApiClient } from "../lib/client";
import { VaultMaintenance } from "./vaultMaintenance";

export const PortabilityService = {
    exportArchive() {
        return ApiClient.download("/portability/export");
    },
    inspectArchive(file) {
        const formData = new FormData();
        formData.append("file", file, file.name || "careeros-backup.zip");
        return ApiClient.postMultipart("/portability/inspect", formData, { timeoutMs: 120_000 });
    },
    async restoreArchive(file) {
        const formData = new FormData();
        formData.append("file", file, file.name || "careeros-backup.zip");
        let result;
        try {
            result = await ApiClient.postMultipart("/portability/restore", formData, {
                timeoutMs: 120_000,
                suppressGlobalError: true,
                suppressUnauthorizedRefresh: true,
            });
        } catch (error) {
            VaultMaintenance.rememberRestoreArchiveForFailure(error, file);
            VaultMaintenance.handleFailure(error);
            throw error;
        }
        VaultMaintenance.complete();
        return result;
    },
    async eraseLocalData() {
        let result;
        try {
            result = await ApiClient.delete("/portability/erase", {
                headers: { "X-Confirm-Erase": "ERASE-LOCAL-CAREER-DATA" },
                timeoutMs: 120_000,
                suppressGlobalError: true,
                suppressUnauthorizedRefresh: true,
            });
        } catch (error) {
            VaultMaintenance.handleFailure(error);
            throw error;
        }
        VaultMaintenance.complete();
        return result;
    },
};
