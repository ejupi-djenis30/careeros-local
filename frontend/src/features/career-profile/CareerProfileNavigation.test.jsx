import { StrictMode } from "react";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createHashRouter, createMemoryRouter, Link, Outlet, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CAREEROS_BEFORE_LOGOUT_EVENT } from "../../lib/events";
import { careerProfile } from "../../test/fixtures";
import { renderWithI18n } from "../../test/renderWithI18n";
import { CareerProfilePage } from "./CareerProfilePage";

const api = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn() }));
vi.mock("../../services/career", () => ({ CareerService: { getProfile: api.get, saveProfile: api.save } }));
vi.mock("../../services/resumes", () => ({ ResumeService: { listVersions: async () => [] } }));
vi.mock("../../context/AuthContext", () => ({ useAuth: () => ({ user: "synthetic-owner" }) }));
vi.mock("../../context/ToastContext", () => ({ useToast: () => ({ showToast: vi.fn() }) }));
const routers = [];

function workspace({ language = "en", strict = false, hash = false, initialEntries = ["/profile"] } = {}) {
    const routes = [{ element: <><Link to="/jobs">Leave profile</Link><Outlet /></>, children: [
        { path: "/profile", element: <CareerProfilePage /> },
        { path: "/jobs", element: <h1>Synthetic destination</h1> },
    ] }];
    if (hash) window.history.replaceState({}, "", "/#/profile");
    const router = hash ? createHashRouter(routes) : createMemoryRouter(routes, { initialEntries });
    routers.push(router);
    const tree = <RouterProvider router={router} />;
    return { router, ...renderWithI18n(strict ? <StrictMode>{tree}</StrictMode> : tree, { language }) };
}
async function edit(language = "en") {
    const input = await screen.findByLabelText(language === "it" ? "Titolo professionale" : "Professional title");
    await userEvent.clear(input);
    await userEvent.type(input, "New unsaved synthetic title");
    return input;
}
const logoutEvent = (force = false) => new CustomEvent(CAREEROS_BEFORE_LOGOUT_EVENT, { cancelable: true, detail: { force } });

describe("Career Vault draft navigation ownership", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        api.get.mockResolvedValue(careerProfile());
        api.save.mockImplementation(async (payload) => careerProfile({ ...payload, revision: payload.expected_revision + 1 }));
        vi.spyOn(window, "confirm").mockReturnValue(false);
    });
    afterEach(() => {
        routers.splice(0).forEach((router) => router.dispose());
        window.history.replaceState({}, "", "/");
        vi.restoreAllMocks();
    });

    it.each(["en", "it"])("keeps a dirty draft after denied navigation with localized confirmation (%s)", async (language) => {
        const { router } = workspace({ language, strict: true });
        const input = await edit(language);
        await userEvent.click(screen.getByRole("link", { name: "Leave profile" }));
        expect(router.state.location.pathname).toBe("/profile");
        expect(input).toHaveValue("New unsaved synthetic title");
        expect(window.confirm).toHaveBeenCalledExactlyOnceWith(language === "it" ? "Modifiche non salvate. Uscire?" : "Unsaved changes. Leave?");
        expect(api.save).not.toHaveBeenCalled();
    });
    it("discards only after accepted navigation and allows a clean navigation without prompting", async () => {
        const first = workspace();
        await screen.findByLabelText("Professional title");
        await userEvent.click(screen.getByRole("link", { name: "Leave profile" }));
        expect(first.router.state.location.pathname).toBe("/jobs");
        expect(window.confirm).not.toHaveBeenCalled();
        first.unmount();
        const second = workspace();
        await edit();
        window.confirm.mockReturnValue(true);
        await userEvent.click(screen.getByRole("link", { name: "Leave profile" }));
        expect(second.router.state.location.pathname).toBe("/jobs");
        expect(api.save).not.toHaveBeenCalled();
    });
    it("allows navigation after a confirmed save but retains the guard through a failed save and retry", async () => {
        const { router } = workspace();
        await edit();
        api.save.mockRejectedValueOnce(new Error("Synthetic write unavailable"));
        await userEvent.click(screen.getByRole("button", { name: "Save Career Vault" }));
        expect(await screen.findByText("Synthetic write unavailable")).toBeInTheDocument();
        await userEvent.click(screen.getByRole("link", { name: "Leave profile" }));
        expect(router.state.location.pathname).toBe("/profile");
        await userEvent.click(screen.getByRole("button", { name: "Save Career Vault" }));
        await waitFor(() => expect(screen.getByRole("button", { name: "Save Career Vault" })).toBeDisabled());
        window.confirm.mockClear();
        await userEvent.click(screen.getByRole("link", { name: "Leave profile" }));
        expect(router.state.location.pathname).toBe("/jobs");
        expect(window.confirm).not.toHaveBeenCalled();
    });
    it("guards desktop hash routes and browser back, allowing same-document fragments", async () => {
        const { router } = workspace({ hash: true });
        await edit();
        await act(async () => router.navigate("/profile#facts"));
        expect(window.confirm).not.toHaveBeenCalled();
        await act(async () => router.navigate("/jobs"));
        expect(router.state.location.pathname).toBe("/profile");
        window.confirm.mockReturnValue(true);
        await act(async () => router.navigate("/jobs"));
        await act(async () => router.navigate(-1));
        await screen.findByLabelText("Professional title");
        expect(router.state.location.pathname).toBe("/profile");
    });
    it("keeps editor controls disabled while a profile acknowledgement is pending", async () => {
        let finish;
        api.save.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
        workspace();
        const input = await edit();
        await userEvent.click(screen.getByRole("button", { name: "Save Career Vault" }));
        expect(input).toBeDisabled();
        await userEvent.type(input, "must not be editable");
        expect(input).toHaveValue("New unsaved synthetic title");
        await act(async () => finish(careerProfile({ revision: 2, headline: "New unsaved synthetic title" })));
        expect(screen.getByLabelText("Professional title")).toBeEnabled();
        expect(screen.getByLabelText("Professional title")).toHaveValue("New unsaved synthetic title");
    });
    it("resets denied browser-back navigation and permits an explicit discard on the next attempt", async () => {
        const { router } = workspace({ initialEntries: ["/jobs", "/profile"] });
        const input = await edit();
        await act(async () => router.navigate(-1));
        expect(router.state.location.pathname).toBe("/profile");
        expect(input).toHaveValue("New unsaved synthetic title");
        window.confirm.mockReturnValue(true);
        await act(async () => router.navigate(-1));
        expect(router.state.location.pathname).toBe("/jobs");
    });
    it("keeps unload/manual logout protection, never blocks forced locking, and removes listeners on unmount", async () => {
        const view = workspace({ strict: true });
        await edit();
        const unload = new Event("beforeunload", { cancelable: true });
        expect(window.dispatchEvent(unload)).toBe(false);
        expect(window.dispatchEvent(logoutEvent())).toBe(false);
        window.confirm.mockClear();
        expect(window.dispatchEvent(logoutEvent(true))).toBe(true);
        expect(window.confirm).not.toHaveBeenCalled();
        window.confirm.mockReturnValue(true);
        expect(window.dispatchEvent(logoutEvent())).toBe(true);
        view.unmount();
        window.confirm.mockClear();
        expect(window.dispatchEvent(new Event("beforeunload", { cancelable: true }))).toBe(true);
        expect(window.dispatchEvent(logoutEvent())).toBe(true);
        expect(window.confirm).not.toHaveBeenCalled();
    });
});
