import { ApiClient } from "../lib/client";

export const LocalModelService = {
    status({ signal, quiet = false } = {}) {
        return ApiClient.get("/local-model/status", signal, { suppressGlobalError: quiet });
    },
    catalog({ signal } = {}) {
        return ApiClient.get("/local-model/catalog", signal);
    },
    install(modelKey, { signal } = {}) {
        return ApiClient.post("/local-model/install", {
            model_key: modelKey,
            license_accepted: true,
        }, { signal, timeoutMs: 30_000 });
    },
    replace(modelKey, { signal } = {}) {
        return ApiClient.post("/local-model/replace", {
            model_key: modelKey,
            license_accepted: true,
        }, { signal, timeoutMs: 30_000 });
    },
    cancel({ signal } = {}) {
        return ApiClient.post("/local-model/cancel", {}, { signal });
    },
    pause({ signal } = {}) {
        return ApiClient.post("/local-model/pause", {}, { signal });
    },
    resume({ signal } = {}) {
        return ApiClient.post("/local-model/resume", {}, { signal });
    },
    remove({ signal } = {}) {
        return ApiClient.delete("/local-model", { signal, timeoutMs: 60_000 });
    },
    restart({ signal } = {}) {
        return ApiClient.post("/local-model/restart", {}, { signal, timeoutMs: 60_000 });
    },
};
