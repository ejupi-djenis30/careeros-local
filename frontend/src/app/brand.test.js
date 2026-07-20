import { describe, expect, it } from "vitest";
import { brandAssetUrl, CAREEROS_MARK_URL } from "./brand";

describe("CareerOS brand asset URL", () => {
    it("keeps the mark at the application root by default", () => {
        expect(CAREEROS_MARK_URL).toBe("/careeros.svg");
    });

    it("resolves the mark under a hosted subpath", () => {
        expect(brandAssetUrl("/careeros-local/")).toBe("/careeros-local/careeros.svg");
        expect(brandAssetUrl("/careeros-local")).toBe("/careeros-local/careeros.svg");
    });

    it("supports the relative base used by a packaged desktop shell", () => {
        expect(brandAssetUrl("./")).toBe("./careeros.svg");
    });
});
