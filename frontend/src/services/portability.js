import { ApiClient } from "../lib/client";

export const PortabilityService = {
    exportArchive() {
        return ApiClient.download("/portability/export");
    },
    restoreArchive(file) {
        const formData = new FormData();
        formData.append("file", file, file.name || "careeros-backup.zip");
        return ApiClient.postMultipart("/portability/restore", formData, { timeoutMs: 120_000 });
    },
    eraseLocalData() {
        return ApiClient.delete("/portability/erase", {
            headers: { "X-Confirm-Erase": "ERASE-LOCAL-CAREER-DATA" },
            timeoutMs: 120_000,
        });
    },
};
