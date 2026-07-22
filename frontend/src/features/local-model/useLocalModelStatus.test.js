import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocalModelService } from "../../services/localModel";
import { useLocalModelStatus } from "./useLocalModelStatus";

vi.mock("../../services/localModel", () => ({
    LocalModelService: { status: vi.fn() },
}));

describe("useLocalModelStatus", () => {
    beforeEach(() => {
        vi.useFakeTimers();
        vi.clearAllMocks();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it("keeps interval refreshes single-flight", async () => {
        let resolveFirst;
        const first = new Promise((resolve) => { resolveFirst = resolve; });
        LocalModelService.status
            .mockReturnValueOnce(first)
            .mockResolvedValue({ ready: true, available: true, configured_model: "local/model" });

        const view = renderHook(() => useLocalModelStatus({ refreshMs: 10 }));
        await act(async () => { await vi.advanceTimersByTimeAsync(0); });
        expect(LocalModelService.status).toHaveBeenCalledTimes(1);

        await act(async () => { await vi.advanceTimersByTimeAsync(50); });
        expect(LocalModelService.status).toHaveBeenCalledTimes(1);

        await act(async () => {
            resolveFirst({ ready: true, available: true, configured_model: "local/model" });
            await first;
        });
        await act(async () => { await vi.advanceTimersByTimeAsync(10); });
        expect(LocalModelService.status).toHaveBeenCalledTimes(2);

        view.unmount();
    });
});
