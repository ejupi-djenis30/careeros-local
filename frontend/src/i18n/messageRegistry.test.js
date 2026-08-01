import { beforeEach, describe, expect, it, vi } from "vitest";

describe("message registry", () => {
    beforeEach(() => {
        vi.resetModules();
    });

    it("loads and deduplicates only the requested local catalogue", async () => {
        const registry = await import("./messageRegistry");

        expect(registry.hasMessages("en")).toBe(false);
        expect(registry.hasMessages("it")).toBe(false);

        const first = registry.loadMessages("en");
        const duplicate = registry.loadMessages("en");
        expect(duplicate).toBe(first);

        const english = await first;
        expect(english["login.welcome"]).toBe("Welcome back");
        expect(registry.hasMessages("en")).toBe(true);
        expect(registry.hasMessages("it")).toBe(false);

        const italian = await registry.loadMessages("it");
        expect(italian["login.welcome"]).toBe("Bentornato");
        expect(registry.hasMessages("it")).toBe(true);
    });

    it("rejects unsupported or malformed catalogues", async () => {
        const registry = await import("./messageRegistry");

        await expect(registry.loadMessages("de")).rejects.toThrow(/unsupported interface language/i);
        expect(() => registry.registerMessages("de", {})).toThrow(/unsupported interface language/i);
        expect(() => registry.registerMessages("en", null)).toThrow(/invalid message catalogue/i);
    });
});
