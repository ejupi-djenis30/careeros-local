import { ApiClient } from "../lib/client";

export const ApplicationService = {
    list() {
        return ApiClient.get("/applications");
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

