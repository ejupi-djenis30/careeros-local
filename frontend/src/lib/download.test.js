import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveBlob } from "./download";

describe("saveBlob", () => {
    let click;
    let createObjectURL;
    let revokeObjectURL;

    beforeEach(() => {
        vi.useFakeTimers();
        createObjectURL = vi.fn(() => "blob:careeros-download");
        revokeObjectURL = vi.fn();
        vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
        click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    });

    afterEach(() => {
        vi.restoreAllMocks();
        vi.unstubAllGlobals();
        vi.useRealTimers();
        document.body.replaceChildren();
    });

    it("clicks a transient download anchor and revokes its URL after navigation starts", () => {
        const blob = new Blob(["private export"], { type: "text/plain" });
        click.mockImplementation(function inspectAnchor() {
            expect(this.isConnected).toBe(true);
            expect(this.href).toBe("blob:careeros-download");
            expect(this.download).toBe("career-export.txt");
            expect(this.rel).toBe("noopener");
        });

        saveBlob({ blob, filename: "career-export.txt" });

        expect(createObjectURL).toHaveBeenCalledWith(blob);
        expect(click).toHaveBeenCalledOnce();
        expect(document.querySelector('a[href="blob:careeros-download"]')).toBeNull();
        expect(revokeObjectURL).not.toHaveBeenCalled();
        vi.runAllTimers();
        expect(revokeObjectURL).toHaveBeenCalledWith("blob:careeros-download");
    });

    it("uses a stable fallback filename", () => {
        saveBlob({ blob: new Blob(["x"]), filename: "" });

        expect(click.mock.instances[0].download).toBe("download");
    });

    it("removes the anchor and schedules URL cleanup if the browser click fails", () => {
        click.mockImplementation(() => {
            throw new Error("download navigation failed");
        });

        expect(() => saveBlob({ blob: new Blob(["x"]), filename: "x.txt" })).toThrow(
            "download navigation failed",
        );
        expect(document.querySelector('a[href="blob:careeros-download"]')).toBeNull();
        vi.runAllTimers();
        expect(revokeObjectURL).toHaveBeenCalledWith("blob:careeros-download");
    });
});
