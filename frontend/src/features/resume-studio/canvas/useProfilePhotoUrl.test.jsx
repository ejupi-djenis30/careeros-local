import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CAREEROS_API_ERROR_EVENT } from "../../../lib/events";
import { useProfilePhotoUrl } from "./useProfilePhotoUrl";

describe("useProfilePhotoUrl request ownership", () => {
    afterEach(() => { vi.restoreAllMocks(); });

    it("aborts a stale photo request without broadcasting its late failure", async () => {
        let finishFirst;
        const first = new Promise((resolve) => { finishFirst = resolve; });
        const fetchMock = vi.spyOn(globalThis, "fetch").mockReturnValueOnce(first)
            .mockResolvedValueOnce(new Response("image", { headers: { "Content-Type": "image/png" } }));
        const createObjectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:current-photo");
        const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
        const globalError = vi.fn();
        window.addEventListener(CAREEROS_API_ERROR_EVENT, globalError);
        const view = renderHook(({ assetId }) => useProfilePhotoUrl(assetId), { initialProps: { assetId: "previous" } });
        try {
            const firstSignal = fetchMock.mock.calls[0][1].signal;
            await act(async () => { view.rerender({ assetId: "current" }); });
            expect(firstSignal.aborted).toBe(true);
            expect(view.result.current).toBe("blob:current-photo");
            await act(async () => {
                finishFirst(new Response(JSON.stringify({ detail: "Old photo missing" }), {
                    status: 404, headers: { "Content-Type": "application/json" },
                }));
                await first;
            });
            expect(view.result.current).toBe("blob:current-photo");
            expect(createObjectUrl).toHaveBeenCalledTimes(1);
            expect(globalError).not.toHaveBeenCalled();
        } finally {
            view.unmount();
            window.removeEventListener(CAREEROS_API_ERROR_EVENT, globalError);
        }
        expect(revokeObjectUrl).toHaveBeenCalledWith("blob:current-photo");
    });
});
