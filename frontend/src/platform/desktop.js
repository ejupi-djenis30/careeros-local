import { configureApiRuntime } from "../lib/client";

const LOOPBACK_API_PATTERN = /^http:\/\/127\.0\.0\.1:([1-9][0-9]{0,4})\/api\/v1$/;

export function isDesktopShell() {
    return typeof window !== "undefined" && Boolean(window.__TAURI_INTERNALS__);
}

function validateBootstrap(payload) {
    if (!payload || payload.desktop !== true) throw new Error("Native bootstrap response is invalid");
    if (!LOOPBACK_API_PATTERN.test(payload.apiBaseUrl || "")) {
        throw new Error("Native bootstrap returned a non-loopback API URL");
    }
    if (!/^[A-Za-z0-9_-]{43,128}$/.test(payload.sessionToken || "")) {
        throw new Error("Native bootstrap returned an invalid session token");
    }
    if (!/^\d+\.\d+\.\d+/.test(payload.appVersion || "")) {
        throw new Error("Native bootstrap returned an invalid application version");
    }
    return payload;
}

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function waitForReadiness(configuration, { timeoutMs, initialDelayMs }) {
    const deadline = Date.now() + timeoutMs;
    let delayMs = initialDelayMs;
    let lastFailure = "local service is starting";
    while (Date.now() < deadline) {
        try {
            const response = await fetch(`${configuration.apiBaseUrl}/health/ready`, {
                method: "GET",
                cache: "no-store",
                headers: { "X-CareerOS-Session": configuration.sessionToken },
            });
            if (response.ok) {
                const payload = await response.json();
                if (payload.status === "ready") return;
                lastFailure = payload.status || "not ready";
            } else {
                lastFailure = `HTTP ${response.status}`;
            }
        } catch (error) {
            lastFailure = error instanceof Error ? error.message : String(error);
        }
        await wait(delayMs);
        delayMs = Math.min(Math.ceil(delayMs * 1.6), 1000);
    }
    throw new Error(`CareerOS Local service did not become ready: ${lastFailure}`);
}

export async function bootstrapDesktop({ timeoutMs = 90_000, initialDelayMs = 100 } = {}) {
    if (!isDesktopShell()) return { desktop: false, state: "browser" };
    const { invoke } = await import("@tauri-apps/api/core");
    const configuration = validateBootstrap(await invoke("desktop_bootstrap"));
    configureApiRuntime(configuration);
    await waitForReadiness(configuration, { timeoutMs, initialDelayMs });
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
