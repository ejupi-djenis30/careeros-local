import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WorkspaceErrorBoundary } from "./WorkspaceErrorBoundary";
import { reactErrorHandlers } from "../lib/uiDiagnostics";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("WorkspaceErrorBoundary", () => {
    it("renders healthy children without a diagnostic", () => {
        const error = vi.spyOn(console, "error").mockImplementation(() => {});
        render(<WorkspaceErrorBoundary><p>Healthy workspace</p></WorkspaceErrorBoundary>);
        expect(screen.getByText("Healthy workspace")).toBeInTheDocument();
        expect(error).not.toHaveBeenCalled();
    });

    it("preserves the error view while real React catches a private render failure safely", () => {
        const error = vi.spyOn(console, "error").mockImplementation(() => {});
        function BrokenWorkspace() { throw new Error("synthetic-private-career-content"); }
        render(
            <WorkspaceErrorBoundary title="Workspace unavailable" description="Try loading again" reloadLabel="Reload workspace">
                <BrokenWorkspace />
            </WorkspaceErrorBoundary>,
            { onCaughtError: reactErrorHandlers.onCaughtError },
        );
        expect(screen.getByRole("alert")).toHaveTextContent("Workspace unavailable");
        expect(screen.getByText("Try loading again")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Reload workspace" })).toBeEnabled();
        expect(error.mock.calls).toEqual([["ui_failure code=react_caught"]]);
    });
});
