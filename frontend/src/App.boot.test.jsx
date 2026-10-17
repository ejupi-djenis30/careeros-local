import { act, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderWithI18n } from "./test/renderWithI18n";
import { AuthenticatedApp } from "./App";

const boot = vi.hoisted(() => ({ auth: { isLoggedIn: false, maintenanceSession: null }, routerImported: vi.fn() }));
vi.mock("react-router", () => {
    boot.routerImported();
    return { createBrowserRouter: vi.fn(() => ({})), createHashRouter: vi.fn(() => ({})), RouterProvider: () => null };
});
vi.mock("./context/AuthContext", () => ({ AuthProvider: ({ children }) => children, useAuth: () => boot.auth }));
vi.mock("./components/Login", () => ({ Login: () => <main data-testid="login" /> }));
vi.mock("./components/RecoveryShell", () => ({ RecoveryShell: () => <main data-testid="recovery" /> }));

describe("public session boot", () => {
    it("does not import or construct the data router for login or recovery", async () => {
        const view = renderWithI18n(<AuthenticatedApp />);
        expect(screen.getByTestId("login")).toBeInTheDocument();
        await act(async () => { await Promise.resolve(); });
        expect(boot.routerImported).not.toHaveBeenCalled();
        boot.auth.maintenanceSession = { sessionState: "restore_pending" };
        view.rerender(<AuthenticatedApp />);
        expect(screen.getByTestId("recovery")).toBeInTheDocument();
        expect(boot.routerImported).not.toHaveBeenCalled();
    });
});
