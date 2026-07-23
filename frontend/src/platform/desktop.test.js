import { afterEach, describe, expect, it, vi } from "vitest";

const invoke = vi.fn();
const save = vi.fn();
const open = vi.fn();
const writeFile = vi.fn();
const readFile = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ save, open }));
vi.mock("@tauri-apps/plugin-fs", () => ({ writeFile, readFile }));

import { resetApiRuntime } from "../lib/client";
import {
    bootstrapDesktop,
    isDesktopShell,
    openBackupWithNativeDialog,
    reportDesktopReady,
    saveBackupWithNativeDialog,
} from "./desktop";

describe("desktop bootstrap", () => {
    afterEach(() => {
        delete window.__TAURI_INTERNALS__;
        invoke.mockReset();
        save.mockReset();
        open.mockReset();
        writeFile.mockReset();
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
        expect(fetchMock.mock.calls[0][1].headers["X-CareerOS-Session"]).toBe(token);
    });

    it("uses scoped native dialogs for backup save and restore", async () => {
        window.__TAURI_INTERNALS__ = {};
        save.mockResolvedValue("C:/Users/DemoUser/backup.zip");
        open.mockResolvedValue("C:/Users/DemoUser/backup.zip");
        readFile.mockResolvedValue(new Uint8Array([80, 75, 3, 4]));
        const blob = { arrayBuffer: vi.fn().mockResolvedValue(Uint8Array.from([1, 2, 3]).buffer) };

        await expect(saveBackupWithNativeDialog({ blob, filename: "backup.zip" })).resolves.toBe(true);
        const selected = await openBackupWithNativeDialog();

        expect(writeFile).toHaveBeenCalledWith(
            "C:/Users/DemoUser/backup.zip",
            new Uint8Array([1, 2, 3]),
        );
        expect(selected.name).toBe("backup.zip");
        expect(selected.type).toBe("application/zip");
    });
});
