import { beforeEach, describe, expect, it, vi } from "vitest";
import en from "../../i18n/locales/en";
import itMessages from "../../i18n/locales/it";

describe("on-route provider messages", () => {
    beforeEach(() => { vi.resetModules(); });

    it("keeps provider vocabulary out of boot catalogues and deduplicates the selected local load", async () => {
        expect(Object.keys(en).some((key) => key.startsWith("providers."))).toBe(false);
        expect(Object.keys(itMessages).some((key) => key.startsWith("providers."))).toBe(false);
        const { loadProviderMessages } = await import("./providerMessages");
        const first = loadProviderMessages("it");
        expect(loadProviderMessages("it")).toBe(first);
        const messages = await first;
        expect(messages["providers.title"]).toBe("Aggiungi le tue sorgenti di lavoro");
        expect(await loadProviderMessages("it")).toBe(messages);
        await expect(loadProviderMessages("de")).rejects.toThrow("Unsupported provider language");
    });

    it("uses the selected feature catalogue and preserves interpolation and shared fallback", async () => {
        const { createProviderTranslator, loadProviderMessages } = await import("./providerMessages");
        const messages = await loadProviderMessages("it");
        const fallback = vi.fn((key) => key);
        const translate = createProviderTranslator(messages, fallback);
        expect(translate("providers.imported", { count: 3 })).toBe("Importati 3 provider.");
        expect(translate("providers.testConsent", { name: "Example" })).toContain("Example");
        expect(translate("providers.providerMeta", { key: "example", adapter: "JSON", revision: 4 })).toContain("4");
        expect(translate("shell.loading")).toBe("shell.loading");
        expect(fallback).toHaveBeenCalledWith("shell.loading", {});
    });
});
