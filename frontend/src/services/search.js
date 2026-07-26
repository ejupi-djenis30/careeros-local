import { ApiClient } from "../lib/client";

export const SearchService = {
    start(profile) {
        return ApiClient.post("/search/start", profile, { suppressGlobalError: true });
    },

    getStatus(profileId) {
        return ApiClient.get(`/search/status/${profileId}`);
    },

    getAllStatuses(signal, options = {}) {
        return ApiClient.get("/search/status/all", signal, options);
    },

    getProfiles(options = {}) {
        return ApiClient.get("/profiles/", undefined, options);
    },

    getProfileOverview({ page = 1, pageSize = 100, ...options } = {}) {
        return ApiClient.get(
            `/profiles/overview?page=${page}&page_size=${pageSize}`,
            undefined,
            options,
        );
    },

    async getProfileSummaries(options = {}) {
        const pageSize = 200;
        const summaries = [];
        let page = 1;
        let totalPages = 1;

        while (page <= totalPages) {
            const response = await SearchService.getProfileOverview({
                ...options,
                page,
                pageSize,
            });
            if (!Array.isArray(response?.items)) return summaries;
            summaries.push(...response.items);

            const reportedTotalPages = Number(response.total_pages);
            totalPages = Number.isInteger(reportedTotalPages) && reportedTotalPages >= 0
                ? reportedTotalPages
                : page;
            if (totalPages > 100) {
                throw new Error("PROFILE_OVERVIEW_PAGE_LIMIT_EXCEEDED");
            }
            page += 1;
        }

        return summaries;
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
