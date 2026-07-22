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
    createTask(id, data) {
        return ApiClient.post(`/applications/${encodeURIComponent(id)}/tasks`, data);
    },
    updateTask(id, taskId, data) {
        return ApiClient.patch(`/applications/${encodeURIComponent(id)}/tasks/${encodeURIComponent(taskId)}`, data);
    },
    downloadTaskCalendar(id) {
        return ApiClient.download(`/applications/${encodeURIComponent(id)}/tasks/calendar.ics`);
    },
    publishDossier(id, data) {
        return ApiClient.post(`/applications/${encodeURIComponent(id)}/dossiers`, data);
    },
    downloadDossier(id, dossierId) {
        return ApiClient.download(`/applications/${encodeURIComponent(id)}/dossiers/${encodeURIComponent(dossierId)}/download`);
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
