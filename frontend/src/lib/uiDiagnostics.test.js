import { afterEach, describe, expect, it, vi } from "vitest";
import { reactErrorHandlers, reportUiFailure } from "./uiDiagnostics";

afterEach(() => vi.restoreAllMocks());

describe("content-free UI diagnostics", () => {
    it("retains an operation code without forwarding supplied error content", () => {
        const error = vi.spyOn(console, "error").mockImplementation(() => {});
        const privateError = new Error("synthetic-private-message");
        reportUiFailure("jobs_fetch", privateError);
        expect(error.mock.calls).toEqual([["ui_failure code=jobs_fetch"]]);
    });

    it("retains the existing warning severity for failed job-view recording", () => {
        const warning = vi.spyOn(console, "warn").mockImplementation(() => {});
        reportUiFailure("job_view");
        expect(warning.mock.calls).toEqual([["ui_failure code=job_view"]]);
    });

    it.each(["synthetic-private-code", "jobs_fetch\nsynthetic-private-data", null, Symbol("private")])(
        "maps untrusted operation values to a constant without echoing them",
        (operation) => {
            const error = vi.spyOn(console, "error").mockImplementation(() => {});
            reportUiFailure(operation);
            expect(error.mock.calls).toEqual([["ui_failure code=unknown"]]);
        },
    );

    it("does not inspect or stringify error objects and React error metadata", () => {
        const error = vi.spyOn(console, "error").mockImplementation(() => {});
        const privateValue = new Proxy({}, { get() { throw new Error("must not inspect private data"); } });
        reportUiFailure(privateValue);
        reactErrorHandlers.onCaughtError(privateValue, privateValue);
        reactErrorHandlers.onUncaughtError(privateValue, privateValue);
        reactErrorHandlers.onRecoverableError(privateValue, privateValue);
        expect(error.mock.calls).toEqual([
            ["ui_failure code=unknown"],
            ["ui_failure code=react_caught"],
            ["ui_failure code=react_uncaught"],
            ["ui_failure code=react_recoverable"],
        ]);
    });
});
