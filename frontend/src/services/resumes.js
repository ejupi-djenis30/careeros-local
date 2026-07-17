import { ApiClient } from "../lib/client";

export const ResumeService = {
    list() {
        return ApiClient.get("/resumes");
    },
    get(id) {
        return ApiClient.get(`/resumes/${encodeURIComponent(id)}`);
    },
    create(data) {
        return ApiClient.post("/resumes", data, { timeoutMs: 60_000 });
    },
    generate(data) {
        return ApiClient.post("/resumes/generate", data, { timeoutMs: 60_000 });
    },
    update(id, data) {
        return ApiClient.put(`/resumes/${encodeURIComponent(id)}`, data, { timeoutMs: 60_000 });
    },
    duplicate(id, data = {}) {
        return ApiClient.post(`/resumes/${encodeURIComponent(id)}/duplicate`, data, { timeoutMs: 60_000 });
    },
    promoteClaim(id, data) {
        return ApiClient.post(`/resumes/${encodeURIComponent(id)}/claims/promote`, data, { timeoutMs: 60_000 });
    },
    sync(id, data) {
        return ApiClient.post(`/resumes/${encodeURIComponent(id)}/sync`, data, { timeoutMs: 60_000 });
    },
    publish(id) {
        return ApiClient.post(`/resumes/${encodeURIComponent(id)}/publish`, {}, { timeoutMs: 120_000 });
    },
    remove(id) {
        return ApiClient.delete(`/resumes/${encodeURIComponent(id)}`);
    },
    downloadArtifact(id) {
        return ApiClient.download(`/resume-artifacts/${encodeURIComponent(id)}`);
    },
};
