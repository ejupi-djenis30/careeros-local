import { StrictMode } from "react";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, Link, Outlet, RouterProvider } from "react-router";
import { careerProfile } from "../test/fixtures";
import { renderWithI18n as render } from "../test/renderWithI18n";
import { NewSearchPage } from "./NewSearchPage";

const api = vi.hoisted(() => ({ start: vi.fn(), getProfile: vi.fn(), getProfileSummaries: vi.fn(), showToast: vi.fn(), stopSearch: vi.fn() }));
vi.mock("../services/search", () => ({ SearchService: { start: api.start, getProfileSummaries: api.getProfileSummaries, stopSearch: api.stopSearch } }));
vi.mock("../services/career", () => ({ CareerService: { getProfile: api.getProfile } }));
vi.mock("../context/ToastContext", () => ({ useToast: () => ({ showToast: api.showToast }) }));

const prefill = { role_description: "Synthetic backend engineer", location_filter: "Zurich", profile_source: "career_vault", max_distance: 50 };
function deferred() {
    let resolve, reject;
    const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
    return { promise, resolve, reject };
}
function renderPage({ strict = false } = {}) {
    const router = createMemoryRouter([{
        element: <><Link to="/elsewhere">Leave search</Link><Outlet /></>,
        children: [
            { path: "/search", element: <NewSearchPage /> },
            { path: "/elsewhere", element: <h1>Other workspace</h1> },
            { path: "/progress", element: <h1>Search progress</h1> },
        ],
    }], { initialEntries: [{ pathname: "/search", state: { prefillProfile: prefill } }] });
    const page = <RouterProvider router={router} />;
    return { ...render(strict ? <StrictMode>{page}</StrictMode> : page), router };
}
async function start(user) {
    await screen.findByText("Revision 3");
    await user.click(screen.getByRole("button", { name: "Start search", exact: true }));
    await waitFor(() => expect(api.start).toHaveBeenCalled());
}

describe("NewSearchPage request ownership", () => {
    beforeEach(() => {
        vi.resetAllMocks();
        api.getProfile.mockResolvedValue(careerProfile());
        api.getProfileSummaries.mockResolvedValue([]);
    });

    it.each([false, true])("opens acknowledged progress once (StrictMode: %s)", async (strict) => {
        api.start.mockResolvedValue({ profile_id: 42 });
        const { router } = renderPage({ strict });
        await start(userEvent.setup());
        expect(await screen.findByRole("heading", { name: "Search progress" })).toBeInTheDocument();
        expect(router.state.location.search).toBe("?pid=42");
        expect(api.start).toHaveBeenCalledTimes(1);
        expect(api.stopSearch).not.toHaveBeenCalled();
    });

    it("invalidates a pending start when its route is left without stopping accepted work", async () => {
        const pending = deferred();
        api.start.mockReturnValue(pending.promise);
        const { router } = renderPage();
        const user = userEvent.setup();
        await start(user);
        await user.click(screen.getByRole("link", { name: "Leave search" }));
        await act(async () => { pending.resolve({ profile_id: 42 }); await pending.promise; });
        expect(router.state.location.pathname).toBe("/elsewhere");
        expect(api.start.mock.calls[0][1].signal.aborted).toBe(true);
        expect(api.start).toHaveBeenCalledTimes(1);
        expect(api.stopSearch).not.toHaveBeenCalled();
    });

    it("preserves a newly mounted form and request when an older start completes", async () => {
        const old = deferred(), current = deferred();
        api.start.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
        const { router } = renderPage();
        const user = userEvent.setup();
        await start(user);
        await user.click(screen.getByRole("link", { name: "Leave search" }));
        await act(async () => { await router.navigate("/search", { state: { prefillProfile: { ...prefill, role_description: "New synthetic role" } } }); });
        await start(user);
        await act(async () => { old.resolve({ profile_id: 1 }); await old.promise; });
        expect(router.state.location.pathname).toBe("/search");
        expect(screen.getByLabelText(/Role description/)).toHaveValue("New synthetic role");
        expect(screen.getByRole("button", { name: /Starting/ })).toBeDisabled();
        await act(async () => { current.resolve({ profile_id: 2 }); await current.promise; });
        expect(router.state.location.search).toBe("?pid=2");
        expect(api.start).toHaveBeenCalledTimes(2);
        expect(api.stopSearch).not.toHaveBeenCalled();
    });

    it("owns a replacement entry on the same search route", async () => {
        const old = deferred();
        api.start.mockReturnValue(old.promise);
        const { router } = renderPage();
        await start(userEvent.setup());
        await act(async () => { await router.navigate("/search", { state: { prefillProfile: { ...prefill, role_description: "Replacement role" } } }); });
        await screen.findByText("Revision 3");
        await act(async () => { old.resolve({ profile_id: 42 }); await old.promise; });
        expect(router.state.location.pathname).toBe("/search");
        expect(screen.getByLabelText(/Role description/)).toHaveValue("Replacement role");
        expect(screen.getByRole("button", { name: "Start search", exact: true })).toBeEnabled();
    });

    it("retains current inputs after failure and retries only after an explicit submission", async () => {
        api.start.mockRejectedValueOnce(new Error("Synthetic start unavailable")).mockResolvedValueOnce({ profile_id: 42 });
        const { router } = renderPage();
        const user = userEvent.setup();
        await start(user);
        expect(await screen.findByText(/Synthetic start unavailable/)).toBeInTheDocument();
        expect(screen.getByLabelText(/Role description/)).toHaveValue(prefill.role_description);
        expect(api.start).toHaveBeenCalledTimes(1);
        await user.click(screen.getByRole("button", { name: "Start search", exact: true }));
        await screen.findByRole("heading", { name: "Search progress" });
        expect(router.state.location.search).toBe("?pid=42");
        expect(api.start).toHaveBeenCalledTimes(2);
    });

    it("ignores stale rejection and abort errors without exposing an error in another session", async () => {
        const pending = deferred();
        api.start.mockReturnValue(pending.promise);
        const { router } = renderPage();
        const user = userEvent.setup();
        await start(user);
        await user.click(screen.getByRole("link", { name: "Leave search" }));
        await act(async () => { pending.reject(new DOMException("Aborted", "AbortError")); await pending.promise.catch(() => {}); });
        expect(router.state.location.pathname).toBe("/elsewhere");
        expect(screen.queryByRole("alert")).not.toBeInTheDocument();
        expect(api.showToast).not.toHaveBeenCalled();
        expect(api.stopSearch).not.toHaveBeenCalled();
    });

    it("allows explicit retry after current cancellation without an automatic second start", async () => {
        api.start.mockRejectedValue(new DOMException("Aborted", "AbortError"));
        const { router } = renderPage();
        await start(userEvent.setup());
        await waitFor(() => expect(screen.getByRole("button", { name: "Start search", exact: true })).toBeEnabled());
        expect(router.state.location.pathname).toBe("/search");
        expect(screen.queryByRole("alert")).not.toBeInTheDocument();
        expect(screen.queryByText(/Aborted/)).not.toBeInTheDocument();
        expect(api.start).toHaveBeenCalledTimes(1);
        expect(api.stopSearch).not.toHaveBeenCalled();
    });

    it("submits only once when form-submit events arrive during a pending start", async () => {
        const pending = deferred();
        api.start.mockReturnValue(pending.promise);
        renderPage();
        await screen.findByText("Revision 3");
        const form = screen.getByRole("button", { name: "Start search", exact: true }).closest("form");
        act(() => { fireEvent.submit(form); fireEvent.submit(form); });
        expect(api.start).toHaveBeenCalledTimes(1);
        await act(async () => { pending.resolve({ profile_id: 42 }); await pending.promise; });
    });
});
