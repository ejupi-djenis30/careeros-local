import { ApiClient, API_BASE } from "../lib/client";

export const SearchService = {
    start(profile) {
        return ApiClient.post("/search/start", profile);
    },

    getStatus(profileId) {
        return ApiClient.get(`/search/status/${profileId}`);
    },

    getAllStatuses() {
        return ApiClient.get("/search/status/all");
    },

    getProfiles() {
        return ApiClient.get("/profiles/");
    },

    uploadCV(file) {
        const formData = new FormData();
        formData.append("file", file);
        return ApiClient.postMultipart("/search/upload-cv", formData);
    },

    toggleSchedule(profileId, enabled, intervalHours = null) {
        const body = { enabled };
        if (intervalHours !== null) body.interval_hours = intervalHours;
        return ApiClient.patch(`/profiles/${profileId}/schedule`, body);
    },

    deleteProfile(profileId) {
        return ApiClient.delete(`/profiles/${profileId}`);
    },

    stopSearch(profileId) {
        return ApiClient.post(`/search/stop/${profileId}`);
    }
};
