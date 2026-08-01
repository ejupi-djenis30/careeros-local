import { describe, expect, it } from "vitest";
import { safeExternalUrl, safeMailto } from "./safeUrl";

describe("safeUrl", () => {
    it("allows canonical HTTPS external links", () => {
        expect(safeExternalUrl("https://example.test/job")).toBe("https://example.test/job");
        expect(safeExternalUrl("https://bücher.example/job")).toBe("https://xn--bcher-kva.example/job");
    });

    it("rejects all cleartext, relative, script and credential-bearing URLs", () => {
        expect(safeExternalUrl("http://example.test/job")).toBeNull();
        expect(safeExternalUrl("http://192.168.1.20/job")).toBeNull();
        expect(safeExternalUrl("http://localhost:8000/path")).toBeNull();
        expect(safeExternalUrl("http://127.255.255.254/path")).toBeNull();
        expect(safeExternalUrl("http://[::1]:8000/path")).toBeNull();
        expect(safeExternalUrl("http://localhost.example.test/job")).toBeNull();
        expect(safeExternalUrl("http://bücher.example/job")).toBeNull();
        expect(safeExternalUrl("http://[::ffff:127.0.0.1]/job")).toBeNull();
        expect(safeExternalUrl("//example.test/job")).toBeNull();
        expect(safeExternalUrl("javascript:alert(1)")).toBeNull();
        expect(safeExternalUrl("https://user:secret@example.test/job")).toBeNull();
        expect(safeExternalUrl("https:\\example.test\\job")).toBeNull();
        expect(safeExternalUrl("https://example.test/\tjob")).toBeNull();
        expect(safeExternalUrl("http://user:secret@localhost:8000/job")).toBeNull();
        expect(safeExternalUrl("not a url")).toBeNull();
    });

    it("rejects mail header injection", () => {
        expect(safeMailto("candidate@example.test")).toBe("mailto:candidate@example.test");
        expect(safeMailto("candidate+jobs@bücher.example"))
            .toBe("mailto:candidate%2Bjobs@xn--bcher-kva.example");
        expect(safeMailto("candidate@example.test\r\nBcc:attacker@example.test")).toBeNull();
        expect(safeMailto("candidate@example.test?subject=unsafe")).toBeNull();
        expect(safeMailto("candidate@@example.test")).toBeNull();
        expect(safeMailto("candidate @example.test")).toBeNull();
        expect(safeMailto("candidate@localhost")).toBeNull();
    });
});
