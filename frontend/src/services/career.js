import { ApiClient } from "../lib/client";

export const CareerService = {
    getProfile(options = {}) {
        return ApiClient.get("/career-profile", undefined, options);
    },
    getSummary(options = {}) {
        return ApiClient.get("/career-profile/summary", undefined, options);
    },
    saveProfile(profile) {
        return ApiClient.put("/career-profile", profile);
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
