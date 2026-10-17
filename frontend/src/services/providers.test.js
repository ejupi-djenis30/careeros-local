import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "../lib/client";
import { ProviderService } from "./providers";

describe("ProviderService transport boundaries", () => {
    afterEach(() => { vi.restoreAllMocks(); });

    it("forwards cancellation and local error ownership to provider mutations", async () => {
        const post = vi.spyOn(ApiClient, "post").mockResolvedValue({});
        const signal = new AbortController().signal;
        await ProviderService.test("provider", { allow_network: true, query: "typed query" }, signal);
        expect(post).toHaveBeenCalledWith("/job-providers/provider/test", { allow_network: true, query: "typed query" },
            { suppressGlobalError: true, timeoutMs: 65_000, signal });
        await ProviderService.importPack("swiss.core", false, signal);
        expect(post).toHaveBeenLastCalledWith("/job-providers/packs/swiss.core/import", { activate: false },
            { suppressGlobalError: true, timeoutMs: 65_000, signal });
    });

    it("sends optimistic revisions without adding activation or external authority", async () => {
        const patch = vi.spyOn(ApiClient, "patch").mockResolvedValue({});
        const remove = vi.spyOn(ApiClient, "delete").mockResolvedValue(null);
        const signal = new AbortController().signal;
        await ProviderService.setState("provider", 4, true, signal);
        expect(patch).toHaveBeenCalledWith("/job-providers/provider/state", { expected_revision: 4, enabled: true },
            { suppressGlobalError: true, timeoutMs: 65_000, signal });
        await ProviderService.remove("provider", 4, signal);
        expect(remove).toHaveBeenCalledWith("/job-providers/provider?expected_revision=4",
            { suppressGlobalError: true, timeoutMs: 65_000, signal });
    });

    it("rejects traversal-bearing identifiers before credentials or fetch", async () => {
        const fetch = vi.spyOn(globalThis, "fetch");
        await expect(ProviderService.importPack("../../private", false)).rejects.toThrow(/traversal|separators/);
        await expect(ProviderService.update("../private", {})).rejects.toThrow(/traversal|separators/);
        expect(fetch).not.toHaveBeenCalled();
    });
});
