import { ApiClient } from "../lib/client";

export const ApplicationService = {
    list(options = {}) {
        return ApiClient.get("/applications", undefined, options);
    },
    get(id) {
        return ApiClient.get(`/applications/${encodeURIComponent(id)}`);
    },
    create(data) {
        return ApiClient.post("/applications", data);
    },
    addEvent(id, data) {
        return ApiClient.post(`/applications/${encodeURIComponent(id)}/events`, data);
    },
};
