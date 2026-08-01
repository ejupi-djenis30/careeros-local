import { ApiClient } from "../lib/client";
import { VaultMaintenance } from "./vaultMaintenance";

export const CareerService = {
    getProfile(options = {}) {
        return ApiClient.get("/career-profile", undefined, options);
    },
    getSummary(options = {}) {
        return ApiClient.get("/career-profile/summary", undefined, options);
    },
    getJobSources(options = {}) {
        return ApiClient.get("/search/sources", undefined, options);
    },
    saveProfile(profile) {
        return ApiClient.put("/career-profile", profile);
    },
    async resetVault() {
        let result;
        try {
            result = await ApiClient.delete("/career-profile", {
                headers: { "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT" },
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
    uploadSource(file) {
        const formData = new FormData();
        formData.append("file", file);
        return ApiClient.postMultipart("/career-profile/sources", formData, { timeoutMs: 60_000 });
    },
    uploadPhoto(file) {
        const formData = new FormData();
        formData.append("file", file);
        return ApiClient.postMultipart("/career-profile/photo", formData, { timeoutMs: 60_000 });
    },
    getPhoto(assetId) {
        return ApiClient.download(`/career-profile/photo/${encodeURIComponent(assetId)}`);
    },
};
