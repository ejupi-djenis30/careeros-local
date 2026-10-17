import { StrictMode, Suspense } from "react";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { renderWithI18n } from "../test/renderWithI18n";

const state = vi.hoisted(() => ({ block: true }));
vi.mock("../platform/desktop", () => ({ isDesktopShell: () => false }));
vi.mock("./AuthenticatedWorkspace", async () => {
    const { Link, useBlocker, useLocation } = await vi.importActual("react-router");
    return { AuthenticatedWorkspace: function WorkspaceFixture() {
        const location = useLocation();
        const blocker = useBlocker(() => state.block);
        return <main><output data-testid="route">{location.pathname}{location.search}</output><Link to="/providers">providers</Link>{blocker.state === "blocked" && <button onClick={() => blocker.reset()}>stay</button>}</main>;
    } };
});

it("keeps browser deep links and data-router blockers through StrictMode and remount", async () => {
    window.history.replaceState(null, "", "/resumes?resumeId=owned-draft");
    const { AuthenticatedRouter } = await import("./AuthenticatedRouter");
    const tree = <StrictMode><Suspense fallback={null}><AuthenticatedRouter /></Suspense></StrictMode>;
    const user = userEvent.setup();
    const first = renderWithI18n(tree);
    expect(await screen.findByTestId("route")).toHaveTextContent("/resumes?resumeId=owned-draft");
    await user.click(screen.getByRole("link", { name: "providers" }));
    expect(await screen.findByRole("button", { name: "stay" })).toBeInTheDocument();
    expect(screen.getByTestId("route")).toHaveTextContent("/resumes?resumeId=owned-draft");
    await user.click(screen.getByRole("button", { name: "stay" }));
    state.block = false;
    await user.click(screen.getByRole("link", { name: "providers" }));
    await waitFor(() => expect(screen.getByTestId("route")).toHaveTextContent("/providers"));
    first.unmount();
    await act(async () => { window.history.pushState(null, "", "/agent-access"); window.dispatchEvent(new PopStateEvent("popstate")); });
    renderWithI18n(tree);
    expect(await screen.findByTestId("route")).toHaveTextContent("/agent-access");
});
