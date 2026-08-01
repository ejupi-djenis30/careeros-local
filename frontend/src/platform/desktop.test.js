import { afterEach, describe, expect, it, vi } from "vitest";

const invoke = vi.fn();
const open = vi.fn();
const readFile = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open }));
vi.mock("@tauri-apps/plugin-fs", () => ({ readFile }));

import { resetApiRuntime } from "../lib/client";
import {
    bootstrapDesktop,
    isDesktopShell,
    openBackupWithNativeDialog,
    reportDesktopReady,
    saveBackupWithNativeDialog,
    sha256Hex,
} from "./desktop";

describe("desktop bootstrap", () => {
    async function archive(value = "portable archive") {
        const bytes = new TextEncoder().encode(value);
        return {
            blob: new Blob([bytes]),
            filename: "backup.zip",
            sha256: await sha256Hex(bytes),
        };
    }

    afterEach(() => {
        delete window.__TAURI_INTERNALS__;
        invoke.mockReset();
        open.mockReset();
        readFile.mockReset();
        resetApiRuntime();
        vi.restoreAllMocks();
    });

    it("keeps browser development mode independent from Tauri", async () => {
        expect(isDesktopShell()).toBe(false);
        await expect(bootstrapDesktop()).resolves.toEqual({ desktop: false, state: "browser" });
        expect(invoke).not.toHaveBeenCalled();
        await expect(reportDesktopReady()).resolves.toBe(false);
        expect(invoke).not.toHaveBeenCalled();
    });

    it("reports a committed frontend tree through the native bridge", async () => {
        window.__TAURI_INTERNALS__ = {};
        invoke.mockResolvedValue(true);

        await expect(reportDesktopReady()).resolves.toBe(true);

        expect(invoke).toHaveBeenCalledWith("desktop_frontend_ready");
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
        expect(fetchMock.mock.calls[0][1].redirect).toBe("error");
        expect(fetchMock.mock.calls[0][1].headers["X-CareerOS-Session"]).toBe(token);
    });

    it.each([
        ["out-of-range port", { apiBaseUrl: "http://127.0.0.1:65536/api/v1" }],
        ["version suffix smuggling", { appVersion: "1.0.0/../../payload" }],
        ["short session token", { sessionToken: "too-short" }],
    ])("rejects invalid native bootstrap metadata: %s", async (_label, override) => {
        window.__TAURI_INTERNALS__ = {};
        invoke.mockResolvedValue({
            desktop: true,
            apiBaseUrl: "http://127.0.0.1:43127/api/v1",
            sessionToken: "native-" + "x".repeat(48),
            appVersion: "1.0.0",
            dataDirectory: "C:/CareerOS",
            backendState: "waiting_ready",
            ...override,
        });
        const fetchMock = vi.spyOn(globalThis, "fetch");

        await expect(bootstrapDesktop()).rejects.toThrow(/native bootstrap/i);

        expect(fetchMock).not.toHaveBeenCalled();
    });

    it("aborts a stalled authenticated readiness probe when its owner unmounts", async () => {
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
        let probeSignal;
        vi.spyOn(globalThis, "fetch").mockImplementation((_url, options) => {
            probeSignal = options.signal;
            return new Promise((_resolve, reject) => {
                probeSignal.addEventListener("abort", () => {
                    reject(new DOMException("Readiness cancelled", "AbortError"));
                }, { once: true });
            });
        });
        const owner = new AbortController();

        const pending = bootstrapDesktop({
            timeoutMs: 90_000,
            initialDelayMs: 1,
            signal: owner.signal,
        });
        await vi.waitFor(() => expect(probeSignal).toBeInstanceOf(AbortSignal));
        owner.abort();

        await expect(pending).rejects.toMatchObject({ name: "AbortError" });
        expect(probeSignal.aborted).toBe(true);
    });

    it("keeps a stalled readiness response body inside the probe deadline", async () => {
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
        vi.spyOn(globalThis, "fetch").mockImplementation((_url, options) => Promise.resolve({
            ok: true,
            status: 200,
            json: () => new Promise((_resolve, reject) => {
                options.signal.addEventListener("abort", () => {
                    reject(new DOMException("Body cancelled", "AbortError"));
                }, { once: true });
            }),
        }));

        await expect(bootstrapDesktop({
            timeoutMs: 25,
            initialDelayMs: 1,
            probeTimeoutMs: 5,
        })).rejects.toThrow(/did not become ready/i);
    });

    it("uses the native backup writer and scoped restore picker", async () => {
        window.__TAURI_INTERNALS__ = {};
        open.mockResolvedValue("C:/Users/DemoUser/backup.zip");
        const payload = await archive();
        invoke.mockResolvedValue({
            saved: true,
            sha256: payload.sha256,
            byteSize: payload.blob.size,
        });
        readFile.mockResolvedValue(new Uint8Array([80, 75, 3, 4]));

        await expect(saveBackupWithNativeDialog(payload)).resolves.toMatchObject({
            saved: true,
            sha256: payload.sha256,
        });
        const selected = await openBackupWithNativeDialog();

        const saveCall = invoke.mock.calls.find(([command]) => command === "desktop_save_verified_backup");
        expect(Array.from(saveCall[1])).toEqual(Array.from(new TextEncoder().encode("portable archive")));
        expect(saveCall[2].headers["X-Content-SHA256"]).toBe(payload.sha256);
        expect(new TextDecoder().decode(
            Uint8Array.from(atob(saveCall[2].headers["X-CareerOS-Dialog-Title"]), (character) => character.charCodeAt(0)),
        )).toBe("Save CareerOS Local backup");
        expect(new TextDecoder().decode(
            Uint8Array.from(atob(saveCall[2].headers["X-CareerOS-Filename"]), (character) => character.charCodeAt(0)),
        )).toBe("backup.zip");
        expect(selected.name).toBe("backup.zip");
        expect(selected.type).toBe("application/zip");
    });

    it("rejects a server checksum mismatch before invoking the native writer", async () => {
        window.__TAURI_INTERNALS__ = {};
        const payload = { ...await archive(), sha256: "0".repeat(64) };

        await expect(saveBackupWithNativeDialog(payload)).rejects.toThrow("downloaded bytes");

        expect(invoke).not.toHaveBeenCalled();
    });
});
