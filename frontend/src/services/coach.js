import { ApiClient } from "../lib/client";

export const CoachService = {
    listConversations() {
        return ApiClient.get("/career-coach/conversations");
    },
    getConversation(id) {
        return ApiClient.get(`/career-coach/conversations/${encodeURIComponent(id)}`);
    },
    deleteConversation(id) {
        return ApiClient.delete(`/career-coach/conversations/${encodeURIComponent(id)}`);
    },
    sendMessage(data) {
        return ApiClient.post("/career-coach/messages", data, { timeoutMs: 120_000 });
    },
};

