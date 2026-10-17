import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "../lib/client";
import { CAREEROS_API_ERROR_EVENT } from "../lib/events";
import { CoachService } from "./coach";

describe("CoachService owned requests", () => {
    beforeEach(() => { ApiClient.invalidateSession(); });
    afterEach(() => { vi.restoreAllMocks(); ApiClient.invalidateSession(); });

    it("preserves the local inference timeout and supports cancellation options", async () => {
        const post = vi.spyOn(ApiClient, "post").mockResolvedValue({});
        const signal = new AbortController().signal;
        const payload = { conversation_id: null, message: "Synthetic question", fact_ids: [], job_ids: [] };
        await CoachService.sendMessage(payload, { signal });
        expect(post).toHaveBeenCalledWith("/career-coach/messages", payload, {
            timeoutMs: 120_000, suppressGlobalError: true, signal,
        });
    });

    it.each(["list", "get", "delete"])("keeps an owned %s error local through the real API client", async (operation) => {
        const globalError = vi.fn();
        window.addEventListener(CAREEROS_API_ERROR_EVENT, globalError);
        const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(
            JSON.stringify({ detail: "Synthetic request failed" }), { status: 409 },
        ));
        const controller = new AbortController();
        const options = { signal: controller.signal, suppressGlobalError: true };
        try {
            const request = operation === "list" ? CoachService.listConversations(options)
                : operation === "get" ? CoachService.getConversation("conversation-a", options)
                    : CoachService.deleteConversation("conversation-a", options);
            await expect(request).rejects.toMatchObject({ status: 409 });
            expect(globalError).not.toHaveBeenCalled();
            expect(fetch.mock.calls[0][1].signal.aborted).toBe(false);
        } finally { window.removeEventListener(CAREEROS_API_ERROR_EVENT, globalError); }
    });
});
