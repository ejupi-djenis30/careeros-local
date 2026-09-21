import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "../lib/client";
import { AgentWorkService } from "./agentWork";

vi.mock("../lib/client", () => ({
    ApiClient: {
        get: vi.fn(),
        post: vi.fn(),
    },
}));

describe("AgentWorkService", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("lists work with default pagination and without query string when no filters", async () => {
        ApiClient.get.mockResolvedValueOnce({ items: [], total: 0 });
        const result = await AgentWorkService.listWork();
        expect(ApiClient.get).toHaveBeenCalledWith("/agent-work?offset=0&limit=25", undefined, {
            suppressGlobalError: true,
        });
        expect(result).toEqual({ items: [], total: 0 });
    });

    it("lists work with custom pagination and state filter", async () => {
        ApiClient.get.mockResolvedValueOnce({ items: [], total: 0 });
        await AgentWorkService.listWork({ offset: 10, limit: 50, state: "queued" });
        expect(ApiClient.get).toHaveBeenCalledWith(
            "/agent-work?offset=10&limit=50&state=queued",
            undefined,
            { suppressGlobalError: true },
        );
    });

    it("creates work with correct payload", async () => {
        const payload = {
            work_kind: "discover",
            grant_id: "grant-123",
            instruction: "Find jobs in Zurich",
        };
        ApiClient.post.mockResolvedValueOnce({ id: "req-1", ...payload });
        const result = await AgentWorkService.createWork(payload);
        expect(ApiClient.post).toHaveBeenCalledWith("/agent-work", payload, {
            signal: undefined,
            suppressGlobalError: true,
        });
        expect(result.id).toBe("req-1");
    });

    it("fetches single work request by ID", async () => {
        ApiClient.get.mockResolvedValueOnce({ request: { id: "req-1" } });
        const result = await AgentWorkService.getWork("req-1");
        expect(ApiClient.get).toHaveBeenCalledWith("/agent-work/req-1", undefined, {
            suppressGlobalError: true,
        });
        expect(result.request.id).toBe("req-1");
    });

    it("cancels work with expected revision", async () => {
        ApiClient.post.mockResolvedValueOnce({ id: "req-1", state: "canceled" });
        const result = await AgentWorkService.cancelWork("req-1", { expected_revision: 2 });
        expect(ApiClient.post).toHaveBeenCalledWith(
            "/agent-work/req-1/cancel",
            { expected_revision: 2 },
            { signal: undefined, suppressGlobalError: true },
        );
        expect(result.state).toBe("canceled");
    });

    it("rejects work with the strict CAS body only", async () => {
        ApiClient.post.mockResolvedValueOnce({ id: "req-1", state: "rejected" });
        const result = await AgentWorkService.rejectWork("req-1", {
            expected_revision: 3,
        });
        expect(ApiClient.post).toHaveBeenCalledWith(
            "/agent-work/req-1/reject",
            { expected_revision: 3 },
            { signal: undefined, suppressGlobalError: true },
        );
        expect(result.state).toBe("rejected");
    });

    it("accepts work with expected revision and payload", async () => {
        ApiClient.post.mockResolvedValueOnce({ receipt: { ok: true } });
        const result = await AgentWorkService.acceptWork("req-1", { expected_revision: 4 });
        expect(ApiClient.post).toHaveBeenCalledWith(
            "/agent-work/req-1/accept",
            { expected_revision: 4 },
            { signal: undefined, suppressGlobalError: true },
        );
        expect(result.receipt.ok).toBe(true);
    });
});
