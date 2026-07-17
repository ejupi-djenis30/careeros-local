import { afterEach, describe, expect, it, vi } from "vitest";

const invoke = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke }));

import { resetApiRuntime } from "../lib/client";
import { bootstrapDesktop, isDesktopShell } from "./desktop";

describe("desktop bootstrap", () => {
    afterEach(() => {
        delete window.__TAURI_INTERNALS__;
        invoke.mockReset();
        resetApiRuntime();
        vi.restoreAllMocks();
    });

    it("keeps browser development mode independent from Tauri", async () => {
        expect(isDesktopShell()).toBe(false);
        await expect(bootstrapDesktop()).resolves.toEqual({ desktop: false, state: "browser" });
        expect(invoke).not.toHaveBeenCalled();
    });

    it("invokes the native bootstrap and waits for authenticated readiness", async () => {
        window.__TAURI_INTERNALS__ = {};
        const token = "native-" + "x".repeat(48);
        invoke.mockResolvedValue({
            desktop: true,
            apiBaseUrl: "http://127.0.0.1:43127/api/v1",
            sessionToken: token,
            appVersion: "1.0.0",
            dataDirectory: "C:/CareerOS",
            backendState: "waiting_ready",
        });
        const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
            new Response(JSON.stringify({ status: "ready" }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
            }),
        );

        const result = await bootstrapDesktop({ timeoutMs: 100, initialDelayMs: 1 });

        expect(result).toMatchObject({ desktop: true, state: "ready", appVersion: "1.0.0" });
        expect(invoke).toHaveBeenCalledWith("desktop_bootstrap");
        expect(fetchMock.mock.calls[0][1].headers["X-CareerOS-Session"]).toBe(token);
    });
});
