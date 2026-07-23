import { afterEach, describe, expect, it, vi } from "vitest";

const openUrl = vi.fn();
vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl }));

import { installExternalNavigation, openExternal } from "./navigation";

describe("desktop external navigation", () => {
    afterEach(() => {
        delete window.__TAURI_INTERNALS__;
        document.body.replaceChildren();
        openUrl.mockReset();
        vi.restoreAllMocks();
    });

    it("uses the scoped native opener instead of navigating the webview", async () => {
        window.__TAURI_INTERNALS__ = {};
        await openExternal("https://jobs.example.test/role");
        expect(openUrl).toHaveBeenCalledWith("https://jobs.example.test/role");
    });

    it("rejects script and credential-bearing targets", async () => {
        await expect(openExternal("javascript:alert(1)")).rejects.toThrow(/not allowed/i);
        await expect(openExternal("https://user:secret@example.test/")).rejects.toThrow(/not allowed/i);
    });

    it("intercepts trusted external anchors in the desktop shell", async () => {
        window.__TAURI_INTERNALS__ = {};
        document.body.innerHTML = '<a href="https://example.test/job"><span>Open</span></a>';
        const uninstall = installExternalNavigation();
        document.querySelector("span").click();
        await vi.waitFor(() => expect(openUrl).toHaveBeenCalledWith("https://example.test/job"));
        uninstall();
    });

    it("reports native opener failures through the localized API error channel", async () => {
        window.__TAURI_INTERNALS__ = {};
        openUrl.mockRejectedValueOnce(new Error("native opener failed"));
        document.body.innerHTML = '<a href="https://example.test/job"><span>Open</span></a>';
        const listener = vi.fn();
        window.addEventListener("careeros:api-error", listener);
        const uninstall = installExternalNavigation();

        document.querySelector("span").click();

        await vi.waitFor(() => expect(listener).toHaveBeenCalledWith(expect.objectContaining({
            detail: { messageKey: "navigation.openFailed" },
        })));
        uninstall();
        window.removeEventListener("careeros:api-error", listener);
    });
});
