import { describe, expect, it } from "vitest";
import { safeExternalUrl, safeMailto } from "./safeUrl";

describe("safeUrl", () => {
    it("allows plain HTTP(S) links without rewriting them", () => {
        expect(safeExternalUrl("https://example.test/job")).toBe("https://example.test/job");
        expect(safeExternalUrl("http://localhost:8000/path")).toBe("http://localhost:8000/path");
    });

    it("rejects script schemes and credential-bearing URLs", () => {
        expect(safeExternalUrl("javascript:alert(1)")).toBeNull();
        expect(safeExternalUrl("https://user:secret@example.test/job")).toBeNull();
        expect(safeExternalUrl("not a url")).toBeNull();
    });

    it("rejects mail header injection", () => {
        expect(safeMailto("candidate@example.test")).toBe("mailto:candidate@example.test");
        expect(safeMailto("candidate@example.test\r\nBcc:attacker@example.test")).toBeNull();
    });
});

