import { ApiClient } from "../lib/client";

const options = { suppressGlobalError: true, timeoutMs: 65_000 };

export const ProviderService = {
    list(signal) {
        return ApiClient.get("/job-providers", signal, options);
    },
    validate(configuration, signal) {
        return ApiClient.post("/job-providers/validate", configuration, { ...options, signal });
    },
    create(configuration, signal) {
        return ApiClient.post("/job-providers", configuration, { ...options, signal });
    },
    importDocument(document, activate = false, signal) {
        return ApiClient.post(
            "/job-providers/import",
            { document, activate },
            { ...options, signal },
        );
    },
    importPack(packId, activate = false, signal) {
        return ApiClient.post(
            `/job-providers/packs/${encodeURIComponent(packId)}/import`,
            { activate },
            { ...options, signal },
        );
    },
    update(id, configuration, signal) {
        return ApiClient.put(`/job-providers/${encodeURIComponent(id)}`, configuration, {
            ...options,
            signal,
        });
    },
    remove(id, revision, signal) {
        return ApiClient.delete(
            `/job-providers/${encodeURIComponent(id)}?expected_revision=${revision}`,
            { ...options, signal },
        );
    },
    setState(id, revision, enabled, signal) {
        return ApiClient.patch(
            `/job-providers/${encodeURIComponent(id)}/state`,
            { expected_revision: revision, enabled },
            { ...options, signal },
        );
    },
    test(id, payload, signal) {
        return ApiClient.post(
            `/job-providers/${encodeURIComponent(id)}/test`,
            payload,
            { ...options, signal },
        );
    },
};
