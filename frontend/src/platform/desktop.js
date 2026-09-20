import { configureApiRuntime } from "../lib/client";

const LOOPBACK_API_PATTERN = /^http:\/\/127\.0\.0\.1:([1-9][0-9]{0,4})\/api\/v1$/;
const APP_VERSION_PATTERN = /^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/;
const ABSOLUTE_PATH_PATTERN = /^(?:[A-Za-z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+|\/)/;
const MCP_SETUP_KEYS = [
    "args",
    "claudeJson",
    "codexToml",
    "command",
    "connectionFile",
    "tokenEnvironmentVariable",
];
const READINESS_PROBE_TIMEOUT_MS = 2_000;

export function isDesktopShell() {
    return typeof window !== "undefined" && Boolean(window.__TAURI_INTERNALS__);
}

function validateBootstrap(payload) {
    if (!payload || payload.desktop !== true) throw new Error("Native bootstrap response is invalid");
    const apiMatch = LOOPBACK_API_PATTERN.exec(payload.apiBaseUrl || "");
    if (!apiMatch || Number(apiMatch[1]) > 65_535) {
        throw new Error("Native bootstrap returned a non-loopback API URL");
    }
    if (!/^[A-Za-z0-9_-]{43,128}$/.test(payload.sessionToken || "")) {
        throw new Error("Native bootstrap returned an invalid session token");
    }
    if (
        typeof payload.appVersion !== "string"
        || payload.appVersion.length > 128
        || !APP_VERSION_PATTERN.test(payload.appVersion)
    ) {
        throw new Error("Native bootstrap returned an invalid application version");
    }
    return payload;
}

function isSafeAbsolutePath(value) {
    const hasControlCharacter = typeof value === "string" && [...value].some((character) => {
        const codePoint = character.codePointAt(0);
        return codePoint <= 31 || codePoint === 127;
    });
    return (
        typeof value === "string"
        && value.length > 0
        && value.length <= 32_767
        && ABSOLUTE_PATH_PATTERN.test(value)
        && !hasControlCharacter
    );
}

function hasExactKeys(value, keys) {
    return (
        value !== null
        && typeof value === "object"
        && !Array.isArray(value)
        && Object.keys(value).sort().join("\n") === [...keys].sort().join("\n")
    );
}

function validateMcpSetup(payload) {
    if (!hasExactKeys(payload, MCP_SETUP_KEYS)) {
        throw new Error("Native MCP setup response is invalid");
    }
    if (!isSafeAbsolutePath(payload.command) || !isSafeAbsolutePath(payload.connectionFile)) {
        throw new Error("Native MCP setup returned an invalid installed path");
    }
    const expectedArgs = [
        "--connection-file",
        payload.connectionFile,
        "--acknowledge-agent-disclosure",
    ];
    if (
        !Array.isArray(payload.args)
        || payload.args.length !== expectedArgs.length
        || payload.args.some((argument, index) => argument !== expectedArgs[index])
    ) {
        throw new Error("Native MCP setup returned invalid launcher arguments");
    }
    if (payload.tokenEnvironmentVariable !== "CAREEROS_MCP_TOKEN") {
        throw new Error("Native MCP setup returned an invalid token variable");
    }
    const expectedCodexToml = (
        "[mcp_servers.careeros]\n"
        + `command = ${JSON.stringify(payload.command)}\n`
        + `args = ${JSON.stringify(expectedArgs)}\n`
        + 'env_vars = ["CAREEROS_MCP_TOKEN"]\n'
    );
    if (payload.codexToml !== expectedCodexToml) {
        throw new Error("Native MCP setup returned an invalid Codex configuration");
    }
    let claudeConfiguration;
    try {
        claudeConfiguration = JSON.parse(payload.claudeJson);
    } catch {
        throw new Error("Native MCP setup returned invalid Claude JSON");
    }
    const servers = claudeConfiguration?.mcpServers;
    const careeros = servers?.careeros;
    if (
        !hasExactKeys(claudeConfiguration, ["mcpServers"])
        || !hasExactKeys(servers, ["careeros"])
        || !hasExactKeys(careeros, ["args", "command"])
        || careeros.command !== payload.command
        || !Array.isArray(careeros.args)
        || careeros.args.length !== expectedArgs.length
        || careeros.args.some((argument, index) => argument !== expectedArgs[index])
    ) {
        throw new Error("Native MCP setup returned an invalid Claude configuration");
    }
    return Object.freeze({
        command: payload.command,
        args: Object.freeze([...expectedArgs]),
        connectionFile: payload.connectionFile,
        tokenEnvironmentVariable: payload.tokenEnvironmentVariable,
        codexToml: payload.codexToml,
        claudeJson: payload.claudeJson,
    });
}

function cancellationError() {
    return new DOMException("Desktop bootstrap was cancelled", "AbortError");
}

function throwIfCancelled(signal) {
    if (signal?.aborted) throw cancellationError();
}

async function waitForOperation(operation, signal) {
    if (!signal) return operation;
    throwIfCancelled(signal);
    let cancel;
    const cancelled = new Promise((_resolve, reject) => {
        cancel = () => reject(cancellationError());
        signal.addEventListener("abort", cancel, { once: true });
    });
    try {
        return await Promise.race([operation, cancelled]);
    } finally {
        signal.removeEventListener("abort", cancel);
    }
}

function wait(milliseconds, signal) {
    return new Promise((resolve, reject) => {
        throwIfCancelled(signal);
        let timeoutId;
        const cleanup = () => signal?.removeEventListener("abort", cancel);
        const complete = () => {
            cleanup();
            resolve();
        };
        const cancel = () => {
            clearTimeout(timeoutId);
            cleanup();
            reject(cancellationError());
        };
        timeoutId = setTimeout(complete, milliseconds);
        signal?.addEventListener("abort", cancel, { once: true });
    });
}

async function readinessRequest(configuration, { timeoutMs, signal }) {
    throwIfCancelled(signal);
    const controller = new AbortController();
    const cancel = () => controller.abort(signal?.reason);
    signal?.addEventListener("abort", cancel, { once: true });
    const timeoutId = setTimeout(
        () => controller.abort("readiness-probe-timeout"),
        timeoutMs,
    );
    try {
        const response = await fetch(`${configuration.apiBaseUrl}/health/ready`, {
            method: "GET",
            cache: "no-store",
            // Never forward the unpersisted native session factor through a
            // redirect, even if the process currently holding the loopback
            // port returns one.
            redirect: "error",
            headers: { "X-CareerOS-Session": configuration.sessionToken },
            signal: controller.signal,
        });
        const payload = response.ok ? await response.json() : null;
        return { response, payload };
    } catch (error) {
        throwIfCancelled(signal);
        throw error;
    } finally {
        clearTimeout(timeoutId);
        signal?.removeEventListener("abort", cancel);
    }
}

async function waitForReadiness(
    configuration,
    { timeoutMs, initialDelayMs, probeTimeoutMs, signal },
) {
    const deadline = Date.now() + timeoutMs;
    let delayMs = initialDelayMs;
    let lastFailure = "local service is starting";
    while (Date.now() < deadline) {
        throwIfCancelled(signal);
        try {
            const { response, payload } = await readinessRequest(configuration, {
                timeoutMs: Math.max(1, Math.min(probeTimeoutMs, deadline - Date.now())),
                signal,
            });
            if (response.ok) {
                if (payload.status === "ready") return;
                lastFailure = payload.status || "not ready";
            } else {
                lastFailure = `HTTP ${response.status}`;
            }
        } catch (error) {
            throwIfCancelled(signal);
            lastFailure = error instanceof Error ? error.message : String(error);
        }
        const remainingMs = deadline - Date.now();
        if (remainingMs <= 0) break;
        await wait(Math.min(delayMs, remainingMs), signal);
        delayMs = Math.min(Math.ceil(delayMs * 1.6), 1000);
    }
    throwIfCancelled(signal);
    throw new Error(`CareerOS Local service did not become ready: ${lastFailure}`);
}

export async function bootstrapDesktop({
    timeoutMs = 90_000,
    initialDelayMs = 100,
    probeTimeoutMs = READINESS_PROBE_TIMEOUT_MS,
    signal,
} = {}) {
    if (!isDesktopShell()) return { desktop: false, state: "browser" };
    const { invoke } = await import("@tauri-apps/api/core");
    const configuration = validateBootstrap(await waitForOperation(
        invoke("desktop_bootstrap"),
        signal,
    ));
    throwIfCancelled(signal);
    configureApiRuntime(configuration);
    await waitForReadiness(configuration, {
        timeoutMs,
        initialDelayMs,
        probeTimeoutMs,
        signal,
    });
    return {
        desktop: true,
        state: "ready",
        appVersion: configuration.appVersion,
        dataDirectory: configuration.dataDirectory,
    };
}

export async function reportDesktopReady() {
    if (!isDesktopShell()) return false;
    const { invoke } = await import("@tauri-apps/api/core");
    return Boolean(await invoke("desktop_frontend_ready"));
}

export async function getDesktopMcpSetup({ signal } = {}) {
    if (!isDesktopShell()) return null;
    const { invoke } = await import("@tauri-apps/api/core");
    const payload = await waitForOperation(invoke("desktop_mcp_setup"), signal);
    throwIfCancelled(signal);
    return validateMcpSetup(payload);
}

const BACKUP_FILTER = [{ name: "CareerOS Local backup", extensions: ["zip"] }];
const SHA256_PATTERN = /^[0-9a-f]{64}$/;

export async function sha256Hex(bytes) {
    const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function verifyArchivePayload({ blob, sha256 }) {
    const expected = String(sha256 || "").trim().toLowerCase();
    if (!(blob instanceof Blob) || !SHA256_PATTERN.test(expected)) {
        throw new Error("The local service returned an unverifiable backup");
    }
    const bytes = new Uint8Array(await blob.arrayBuffer());
    if (await sha256Hex(bytes) !== expected) {
        throw new Error("The backup checksum does not match the downloaded bytes");
    }
    return bytes;
}

function encodeHeaderValue(value) {
    const bytes = new TextEncoder().encode(value);
    let binary = "";
    for (let offset = 0; offset < bytes.length; offset += 8192) {
        binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
    }
    return btoa(binary);
}

export async function saveBackupWithNativeDialog(archive, { title = "Save CareerOS Local backup" } = {}) {
    if (!isDesktopShell()) return null;
    const { invoke } = await import("@tauri-apps/api/core");
    const bytes = await verifyArchivePayload(archive);
    return invoke("desktop_save_verified_backup", bytes, {
        headers: {
            "X-CareerOS-Dialog-Title": encodeHeaderValue(title),
            "X-CareerOS-Filename": encodeHeaderValue(archive.filename),
            "X-Content-SHA256": archive.sha256,
        },
    });
}

export async function openBackupWithNativeDialog({ title = "Open CareerOS Local backup" } = {}) {
    if (!isDesktopShell()) return null;
    const [{ open }, { readFile }] = await Promise.all([
        import("@tauri-apps/plugin-dialog"),
        import("@tauri-apps/plugin-fs"),
    ]);
    const selected = await open({
        title,
        multiple: false,
        directory: false,
        filters: BACKUP_FILTER,
    });
    if (!selected || Array.isArray(selected)) return null;
    const bytes = await readFile(selected);
    const filename = selected.split(/[\\/]/).pop() || "careeros-backup.zip";
    return new File([bytes], filename, { type: "application/zip" });
}

const CAMPAIGN_FILTER = [{ name: "CareerOS campaign", extensions: ["zip"] }];
let nativeCampaignDialogOpen = false;

export async function openCampaignWithNativeDialog({ title = "Open CareerOS campaign" } = {}) {
    if (!isDesktopShell()) return null;
    if (nativeCampaignDialogOpen) return null;
    nativeCampaignDialogOpen = true;
    try {
        const [{ open }, { readFile }] = await Promise.all([
            import("@tauri-apps/plugin-dialog"),
            import("@tauri-apps/plugin-fs"),
        ]);
        const selected = await open({
            title,
            multiple: false,
            directory: false,
            filters: CAMPAIGN_FILTER,
        });
        if (!selected || Array.isArray(selected)) return null;
        const bytes = await readFile(selected);
        const filename = selected.split(/[\\/]/).pop() || "campaign.zip";
        const file = new File([bytes], filename, { type: "application/zip" });
        delete file.path;
        return file;
    } finally {
        nativeCampaignDialogOpen = false;
    }
}
