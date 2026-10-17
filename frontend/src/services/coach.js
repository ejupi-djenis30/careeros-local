import { ApiClient } from "../lib/client";

export const CoachService = {
    listConversations(options = {}) {
        return ApiClient.get("/career-coach/conversations", undefined, options);
    },
    getConversation(id, options = {}) {
        return ApiClient.get(`/career-coach/conversations/${encodeURIComponent(id)}`, undefined, options);
    },
    deleteConversation(id, options = {}) {
        return ApiClient.delete(`/career-coach/conversations/${encodeURIComponent(id)}`, options);
    },
    sendMessage(data, options = {}) {
        return ApiClient.post("/career-coach/messages", data, { timeoutMs: 120_000, suppressGlobalError: true, ...options });
    },
};
