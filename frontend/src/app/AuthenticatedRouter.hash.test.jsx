import { StrictMode, Suspense } from "react";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { renderWithI18n } from "../test/renderWithI18n";

vi.mock("../platform/desktop", () => ({ isDesktopShell: () => true }));
vi.mock("./AuthenticatedWorkspace", async () => {
    const { Link, useLocation } = await vi.importActual("react-router");
    return { AuthenticatedWorkspace: function WorkspaceFixture() {
        const location = useLocation();
        return <main><output data-testid="route">{location.pathname}{location.search}</output><Link to="/providers">providers</Link></main>;
    } };
});

it("preserves Tauri hash deep links when the authenticated router first loads", async () => {
    window.history.replaceState(null, "", "/#/resumes?resumeId=owned-hash-draft");
    const { AuthenticatedRouter } = await import("./AuthenticatedRouter");
    renderWithI18n(<StrictMode><Suspense fallback={null}><AuthenticatedRouter /></Suspense></StrictMode>);
    expect(await screen.findByTestId("route")).toHaveTextContent("/resumes?resumeId=owned-hash-draft");
    await userEvent.setup().click(screen.getByRole("link", { name: "providers" }));
    await waitFor(() => expect(window.location.hash).toBe("#/providers"));
});
