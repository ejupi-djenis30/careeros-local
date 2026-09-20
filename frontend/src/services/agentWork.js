import { ApiClient } from "../lib/client";

export const AgentWorkService = {
    async listWork({ offset = 0, limit = 25, state, signal } = {}) {
        const params = new URLSearchParams();
        if (offset != null) params.append("offset", String(offset));
        if (limit != null) params.append("limit", String(limit));
        if (state) params.append("state", String(state));
        const qs = params.toString();
        const url = qs ? `/agent-work?${qs}` : "/agent-work";
        return ApiClient.get(url, signal, { suppressGlobalError: true });
    },

    async createWork(payload, { signal } = {}) {
        return ApiClient.post("/agent-work", payload, { signal, suppressGlobalError: true });
    },

    async getWork(id, { signal } = {}) {
        return ApiClient.get(`/agent-work/${encodeURIComponent(id)}`, signal, { suppressGlobalError: true });
    },

    async cancelWork(id, { expected_revision }, { signal } = {}) {
        return ApiClient.post(
            `/agent-work/${encodeURIComponent(id)}/cancel`,
            { expected_revision },
            { signal, suppressGlobalError: true },
        );
    },

    async rejectWork(id, { expected_revision }, { signal } = {}) {
        return ApiClient.post(
            `/agent-work/${encodeURIComponent(id)}/reject`,
            { expected_revision },
            { signal, suppressGlobalError: true },
        );
    },

    async acceptWork(id, payload = {}, { signal } = {}) {
        return ApiClient.post(
            `/agent-work/${encodeURIComponent(id)}/accept`,
            payload,
            { signal, suppressGlobalError: true },
        );
    },
};
