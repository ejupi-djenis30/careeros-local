import { ApiClient } from "../lib/client";

export const ApplicationService = {
    list(options = {}) {
        return ApiClient.get("/applications", undefined, options);
    },
    get(id, options = {}) {
        return ApiClient.get(`/applications/${encodeURIComponent(id)}`, options.signal, options);
    },
    create(data) {
        return ApiClient.post("/applications", data);
    },
    addEvent(id, data) {
        return ApiClient.post(`/applications/${encodeURIComponent(id)}/events`, data);
    },
    readiness(id, options = {}) {
        return ApiClient.get(`/applications/${encodeURIComponent(id)}/readiness`, options.signal, options);
    },
    downloadReadiness(id, format) {
        const query = new URLSearchParams({ format });
        return ApiClient.download(`/applications/${encodeURIComponent(id)}/readiness/export?${query}`);
    },
    updatePreparation(id, data) {
        return ApiClient.patch(`/applications/${encodeURIComponent(id)}/preparation`, data);
    },
};
