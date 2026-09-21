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
    getDesktopMcpSetup,
    isDesktopShell,
    openBackupWithNativeDialog,
    openCampaignWithNativeDialog,
    reportDesktopReady,
    saveBackupWithNativeDialog,
    sha256Hex,
} from "./desktop";

function validMcpSetup() {
    const command = "C:\\Program Files\\CareerOS\\careeros-mcp.exe";
    const connectionFile = "C:\\Users\\DemoUser\\AppData\\Roaming\\CareerOS\\mcp\\connection.json";
    const args = [
        "--connection-file",
        connectionFile,
        "--acknowledge-agent-disclosure",
    ];
    return {
        command,
        args,
        connectionFile,
        tokenEnvironmentVariable: "CAREEROS_MCP_TOKEN",
        codexToml: (
            "[mcp_servers.careeros]\n"
            + `command = ${JSON.stringify(command)}\n`
            + `args = ${JSON.stringify(args)}\n`
            + 'env_vars = ["CAREEROS_MCP_TOKEN"]\n'
        ),
        claudeJson: JSON.stringify({
            mcpServers: { careeros: { command, args } },
        }, null, 2),
    };
}

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
        await expect(getDesktopMcpSetup()).resolves.toBeNull();
        expect(invoke).not.toHaveBeenCalled();
    });

    it("returns only the verified installed MCP launcher configuration", async () => {
        window.__TAURI_INTERNALS__ = {};
        const payload = validMcpSetup();
        invoke.mockResolvedValue(payload);

        const configuration = await getDesktopMcpSetup();

        expect(invoke).toHaveBeenCalledWith("desktop_mcp_setup");
        expect(configuration).toEqual(payload);
        expect(Object.keys(configuration).sort()).toEqual(Object.keys(payload).sort());
        expect(configuration.codexToml).not.toContain("careeros_mcp_v1_");
        expect(configuration.claudeJson).not.toContain("CAREEROS_MCP_TOKEN");
        expect(Object.isFrozen(configuration)).toBe(true);
        expect(Object.isFrozen(configuration.args)).toBe(true);
    });

    it.each([
        ["unexpected secret-bearing field", (payload) => ({ ...payload, sessionToken: "secret" })],
        ["relative launcher", (payload) => ({ ...payload, command: "careeros-mcp.exe" })],
        ["changed arguments", (payload) => ({ ...payload, args: ["--desktop-url", "http://127.0.0.1"] })],
        ["changed Codex table", (payload) => ({ ...payload, codexToml: `${payload.codexToml}token = "secret"\n` })],
        ["extra Claude setting", (payload) => ({
            ...payload,
            claudeJson: JSON.stringify({
                mcpServers: {
                    careeros: {
                        command: payload.command,
                        args: payload.args,
                        env: { CAREEROS_MCP_TOKEN: "secret" },
                    },
                },
            }),
        })],
    ])("rejects a native MCP response with %s", async (_label, mutate) => {
        window.__TAURI_INTERNALS__ = {};
        invoke.mockResolvedValue(mutate(validMcpSetup()));

        await expect(getDesktopMcpSetup()).rejects.toThrow(/native MCP setup/i);
    });

    it("cancels a pending native MCP setup when its UI owner unmounts", async () => {
        window.__TAURI_INTERNALS__ = {};
        invoke.mockReturnValue(new Promise(() => {}));
        const owner = new AbortController();

        const pending = getDesktopMcpSetup({ signal: owner.signal });
        owner.abort();

        await expect(pending).rejects.toMatchObject({ name: "AbortError" });
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

    it("reads one explicitly selected campaign ZIP without retaining its native path", async () => {
        window.__TAURI_INTERNALS__ = {};
        open.mockResolvedValue("C:/Users/DemoUser/Private Search/campaign-source.zip");
        readFile.mockResolvedValue(new Uint8Array([80, 75, 3, 4]));

        const selected = await openCampaignWithNativeDialog({
            title: "Import local campaign",
        });

        expect(open).toHaveBeenCalledWith({
            title: "Import local campaign",
            multiple: false,
            directory: false,
            filters: [{ name: "CareerOS campaign", extensions: ["zip"] }],
        });
        expect(readFile).toHaveBeenCalledWith(
            "C:/Users/DemoUser/Private Search/campaign-source.zip",
        );
        expect(selected).toBeInstanceOf(File);
        expect(selected.name).toBe("campaign-source.zip");
        expect(selected.type).toBe("application/zip");
        expect(selected.path).toBeUndefined();
    });

    it("rejects a server checksum mismatch before invoking the native writer", async () => {
        window.__TAURI_INTERNALS__ = {};
        const payload = { ...await archive(), sha256: "0".repeat(64) };

        await expect(saveBackupWithNativeDialog(payload)).rejects.toThrow("downloaded bytes");

        expect(invoke).not.toHaveBeenCalled();
    });
});
