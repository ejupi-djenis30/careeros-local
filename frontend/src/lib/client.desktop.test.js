import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiClient, configureApiRuntime, resetApiRuntime } from "./client";

describe("desktop API runtime", () => {
    afterEach(() => {
        resetApiRuntime();
        vi.restoreAllMocks();
    });

    it("accepts only loopback runtime URLs and adds the per-launch session header", async () => {
        configureApiRuntime({
            apiBaseUrl: "http://127.0.0.1:43127/api/v1",
            sessionToken: "desktop-" + "x".repeat(43),
        });
        const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
            new Response(JSON.stringify({ status: "ready" }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
            }),
        );

        await ApiClient.get("/health/ready");

        expect(fetchMock).toHaveBeenCalledWith(
            "http://127.0.0.1:43127/api/v1/health/ready",
            expect.objectContaining({
                headers: expect.objectContaining({ "X-CareerOS-Session": "desktop-" + "x".repeat(43) }),
            }),
        );
    });

    it("rejects a non-loopback desktop service", () => {
        expect(() => configureApiRuntime({
            apiBaseUrl: "https://example.com/api/v1",
            sessionToken: "desktop-" + "x".repeat(43),
        })).toThrow(/loopback/i);
    });
});
