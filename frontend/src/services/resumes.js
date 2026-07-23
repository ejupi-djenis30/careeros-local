import { ApiClient } from "../lib/client";

export const ResumeService = {
    list(options = {}) {
        return ApiClient.get("/resumes", undefined, options);
    },
    listVersions(options = {}) {
        return ApiClient.get("/resumes/versions", undefined, options);
    },
    get(id, options = {}) {
        return ApiClient.get(`/resumes/${encodeURIComponent(id)}`, undefined, options);
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
    publish(id, name) {
        return ApiClient.post(`/resumes/${encodeURIComponent(id)}/publish`, { name }, { timeoutMs: 120_000 });
    },
    compareVersions(leftId, rightId) {
        const query = new URLSearchParams({ left_id: leftId, right_id: rightId });
        return ApiClient.get(`/resumes/versions/compare?${query}`);
    },
    restoreVersion(id, versionId, expectedRevision) {
        return ApiClient.post(`/resumes/${encodeURIComponent(id)}/versions/${encodeURIComponent(versionId)}/restore`, {
            expected_revision: expectedRevision,
        }, { timeoutMs: 60_000 });
    },
    remove(id) {
        return ApiClient.delete(`/resumes/${encodeURIComponent(id)}`);
    },
    downloadArtifact(id) {
        return ApiClient.download(`/resume-artifacts/${encodeURIComponent(id)}`);
    },
};
