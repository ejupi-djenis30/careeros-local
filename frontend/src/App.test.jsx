import { act, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithI18n as render } from "./test/renderWithI18n";
import { AuthenticatedApp } from "./App";

const authState = vi.hoisted(() => ({
    isLoggedIn: true,
    maintenanceSession: null,
}));

vi.mock("./context/AuthContext", () => ({
    AuthProvider: ({ children }) => children,
    useAuth: () => authState,
}));
vi.mock("./components/Login", () => ({
    Login: () => <main data-testid="login">login</main>,
}));
vi.mock("./components/RecoveryShell", () => ({
    RecoveryShell: () => <main data-testid="recovery">recovery</main>,
}));
vi.mock("./app/AuthenticatedWorkspace", () => ({
    AuthenticatedWorkspace: () => <main data-testid="workspace">workspace</main>,
}));

describe("AuthenticatedApp session boundary", () => {
    beforeEach(() => {
        authState.isLoggedIn = true;
        authState.maintenanceSession = null;
    });

    it("unmounts private toasts when recovery replaces the workspace", async () => {
        const { rerender } = render(<AuthenticatedApp />);
        await screen.findByTestId("workspace");

        act(() => {
            window.dispatchEvent(new CustomEvent("careeros:api-error", {
                detail: { message: "Private application title" },
            }));
        });
        expect(screen.getByText("Private application title")).toBeInTheDocument();

        authState.isLoggedIn = false;
        authState.maintenanceSession = {
            sessionState: "restore_pending",
            reauthRequired: false,
        };
        rerender(<AuthenticatedApp />);

        expect(screen.getByTestId("recovery")).toBeInTheDocument();
        expect(screen.queryByTestId("workspace")).toBeNull();
        expect(screen.queryByText("Private application title")).toBeNull();
    });
});
