import { ApiClient } from "../lib/client";

export const LocalModelService = {
    status({ signal, quiet = false } = {}) {
        return ApiClient.get("/local-model/status", signal, { suppressGlobalError: quiet });
    },
};

