import { ApiClient } from "../lib/client";

export const ResumeService = {
    listTemplates(options = {}) {
        return ApiClient.get("/resumes/templates", undefined, options);
    },
    list(options = {}) {
        return ApiClient.get("/resumes", undefined, options);
    },
    listVersions(options = {}) {
        return ApiClient.get("/resumes/versions", undefined, options);
    },
    get(id, options = {}) {
        return ApiClient.get(`/resumes/${encodeURIComponent(id)}`, undefined, options);
    },
    create(data, options = {}) {
        return ApiClient.post("/resumes", data, { timeoutMs: 60_000, ...options });
    },
    generate(data, options = {}) {
        return ApiClient.post("/resumes/generate", data, { timeoutMs: 60_000, ...options });
    },
    update(id, data, options = {}) {
        return ApiClient.put(`/resumes/${encodeURIComponent(id)}`, data, { timeoutMs: 60_000, ...options });
    },
    duplicate(id, data = {}, options = {}) {
        return ApiClient.post(`/resumes/${encodeURIComponent(id)}/duplicate`, data, { timeoutMs: 60_000, ...options });
    },
    promoteClaim(id, data, options = {}) {
        return ApiClient.post(`/resumes/${encodeURIComponent(id)}/claims/promote`, data, { timeoutMs: 60_000, ...options });
    },
    sync(id, data, options = {}) {
        return ApiClient.post(`/resumes/${encodeURIComponent(id)}/sync`, data, { timeoutMs: 60_000, ...options });
    },
    publish(id, name, options = {}) {
        return ApiClient.post(`/resumes/${encodeURIComponent(id)}/publish`, { name }, { timeoutMs: 120_000, ...options });
    },
    compareVersions(leftId, rightId, options = {}) {
        const query = new URLSearchParams({ left_id: leftId, right_id: rightId });
        return ApiClient.get(`/resumes/versions/compare?${query}`, undefined, options);
    },
    restoreVersion(id, versionId, expectedRevision, options = {}) {
        return ApiClient.post(`/resumes/${encodeURIComponent(id)}/versions/${encodeURIComponent(versionId)}/restore`, {
            expected_revision: expectedRevision,
        }, { timeoutMs: 60_000, ...options });
    },
    remove(id, options = {}) {
        return ApiClient.delete(`/resumes/${encodeURIComponent(id)}`, options);
    },
    downloadArtifact(id) {
        return ApiClient.download(`/resume-artifacts/${encodeURIComponent(id)}`);
    },
};
