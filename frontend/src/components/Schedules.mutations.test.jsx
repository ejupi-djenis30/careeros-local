import React, { StrictMode } from "react";
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithI18n as render } from "../test/renderWithI18n";
import { Schedules } from "./Schedules";

const api = vi.hoisted(() => ({ list: vi.fn(), toggle: vi.fn(), toast: vi.fn() }));
vi.mock("../services/search", () => ({
    SearchService: { getProfileSummaries: api.list, toggleSchedule: api.toggle },
}));
vi.mock("../context/ToastContext", () => ({ useToast: () => ({ showToast: api.toast }) }));

const a = {
    id: 101, name: "Synthetic schedule A", role_description: "Synthetic role",
    schedule_enabled: true, schedule_interval_hours: 12,
};
const b = { ...a, id: 102, name: "Synthetic schedule B" };
function deferred() {
    let resolve, reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return { promise, resolve, reject };
}
async function settle(request, value, reject = false) {
    await act(async () => {
        request[reject ? "reject" : "resolve"](value);
        await request.promise.catch(() => {});
    });
}
async function openSchedules(options) {
    const view = render(<Schedules />, options);
    await screen.findByText(a.name);
    return view;
}
function card(name = a.name) {
    return screen.getByText(name).closest(".col-12");
}
function interval(name = a.name) {
    return within(card(name)).getByRole("spinbutton");
}
function choose(hours, name = a.name) {
    fireEvent.click(within(card(name)).getByRole("button", { name: `${hours}h` }));
}
async function remove(name = a.name) {
    fireEvent.click(within(card(name)).getByRole("button", { name: "Delete campaign" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove schedule" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove", exact: true }));
}

describe("Schedules acknowledged mutation ownership", () => {
    let network;
    beforeEach(() => {
        vi.resetAllMocks();
        api.list.mockResolvedValue([a, b]);
        api.toggle.mockResolvedValue({ ...a, schedule_enabled: false });
        network = vi.fn().mockRejectedValue(new Error("EGRESS_DENIED"));
        vi.stubGlobal("fetch", network);
    });
    afterEach(() => {
        expect(network).not.toHaveBeenCalled();
        vi.unstubAllGlobals();
    });

    it.each(["toggle", "interval", "remove"])("retains the %s ACK and other rows when refresh fails; retry only reads", async (kind) => {
        const write = deferred(), read = deferred();
        const ack = { ...a, schedule_enabled: kind === "interval", schedule_interval_hours: 18 };
        api.toggle.mockReturnValueOnce(write.promise);
        api.list.mockResolvedValueOnce([a, b]).mockReturnValueOnce(read.promise)
            .mockResolvedValueOnce([ack, b]);
        await openSchedules();
        if (kind === "toggle") fireEvent.click(within(card()).getByRole("checkbox"));
        else if (kind === "interval") choose(24);
        else await remove();
        await settle(write, ack);
        expect(screen.getByText(b.name)).toBeInTheDocument();
        if (kind === "interval") expect(interval()).toHaveValue(18);
        else expect(screen.queryByText(a.name)).not.toBeInTheDocument();
        await settle(read, new Error("SYNTHETIC_READ_UNAVAILABLE"), true);
        expect(await screen.findByRole("alert")).toHaveTextContent("Could not refresh schedules. Saved changes are kept.");
        expect(screen.getByText(b.name)).toBeInTheDocument();
        expect(api.toast).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Try again" }));
        await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
        expect(api.list).toHaveBeenCalledTimes(3);
        expect(api.toggle).toHaveBeenCalledTimes(1);
        expect(api.toggle.mock.calls[0][3]).toEqual({ suppressGlobalError: true });
    });

    it.each(["resolve", "reject"])("ignores a late write %s after unmount", async (completion) => {
        const write = deferred();
        api.toggle.mockReturnValueOnce(write.promise);
        const view = await openSchedules();
        fireEvent.click(within(card()).getByRole("checkbox"));
        view.unmount();
        await settle(write, completion === "resolve" ? { ...a, schedule_enabled: false } : new Error("SYNTHETIC_WRITE_UNAVAILABLE"), completion === "reject");
        expect(api.list).toHaveBeenCalledTimes(1);
        expect(api.toast).not.toHaveBeenCalled();
    });

    it("keeps a fresh StrictMode owner independent from the previous pending mutation", async () => {
        const write = deferred();
        api.toggle.mockReturnValueOnce(write.promise);
        const view = render(<StrictMode><Schedules /></StrictMode>);
        await screen.findByText(a.name);
        expect(api.list).toHaveBeenCalledTimes(1);
        fireEvent.click(within(card()).getByRole("checkbox"));
        view.unmount();
        render(<StrictMode><Schedules /></StrictMode>);
        await screen.findByText(a.name);
        await settle(write, { ...a, schedule_enabled: false });
        expect(screen.getByText(a.name)).toBeInTheDocument();
        expect(api.list).toHaveBeenCalledTimes(2);
        expect(api.toast).not.toHaveBeenCalled();
    });

    it("invalidates pre-ACK reads and accepts a later authoritative server change", async () => {
        const oldRead = deferred(), newRead = deferred(), write = deferred();
        api.list.mockResolvedValueOnce([a, b]).mockReturnValueOnce(oldRead.promise)
            .mockReturnValueOnce(newRead.promise);
        api.toggle.mockReturnValueOnce(write.promise);
        await openSchedules();
        fireEvent.click(screen.getByRole("button", { name: "Refresh schedules" }));
        choose(24);
        const oldSignal = api.list.mock.calls[1][0].signal;
        await settle(write, { ...a, schedule_interval_hours: 24 });
        expect(oldSignal.aborted).toBe(true);
        expect(interval()).toHaveValue(24);
        await settle(oldRead, [a, b]);
        expect(interval()).toHaveValue(24);
        await settle(newRead, [{ ...a, schedule_interval_hours: 6 }, b]);
        expect(interval()).toHaveValue(6);
    });

    it("disables all competing controls on the pending row and guards duplicate events", async () => {
        const write = deferred();
        api.toggle.mockReturnValueOnce(write.promise);
        await openSchedules();
        const first = within(card()).getByRole("button", { name: "1h" });
        const second = within(card()).getByRole("button", { name: "3h" });
        act(() => { fireEvent.click(first); fireEvent.click(second); });
        expect(api.toggle).toHaveBeenCalledTimes(1);
        for (const control of within(card()).getAllByRole("button")) expect(control).toBeDisabled();
        expect(interval()).toBeDisabled();
        expect(within(card()).getByRole("checkbox")).toBeDisabled();
        expect(within(card(b.name)).getByRole("checkbox")).toBeEnabled();
        await settle(write, { ...a, schedule_interval_hours: 1 });
    });

    it("retains both independent row ACKs when their refreshes overlap and fail", async () => {
        const first = deferred(), second = deferred(), oldRead = deferred(), newRead = deferred();
        api.toggle.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
        api.list.mockResolvedValueOnce([a, b]).mockReturnValueOnce(oldRead.promise)
            .mockReturnValueOnce(newRead.promise);
        await openSchedules();
        choose(24);
        choose(6, b.name);
        await settle(second, { ...b, schedule_interval_hours: 6 });
        await settle(first, { ...a, schedule_interval_hours: 24 });
        await settle(oldRead, [a, b]);
        await settle(newRead, new Error("SYNTHETIC_READ_UNAVAILABLE"), true);
        expect(interval()).toHaveValue(24);
        expect(interval(b.name)).toHaveValue(6);
        expect(api.toggle).toHaveBeenCalledTimes(2);
    });

    it("does not close a new confirmation when an earlier removal is acknowledged", async () => {
        const write = deferred();
        api.toggle.mockReturnValueOnce(write.promise);
        api.list.mockResolvedValueOnce([a, b]).mockRejectedValueOnce(new Error("SYNTHETIC_READ_UNAVAILABLE"));
        await openSchedules();
        await remove();
        fireEvent.click(within(card(b.name)).getByRole("button", { name: "Delete campaign" }));
        await settle(write, { ...a, schedule_enabled: false });
        const dialog = screen.getByRole("dialog", { name: "Remove schedule" });
        fireEvent.click(within(dialog).getByRole("button", { name: "Cancel", exact: true }));
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
        expect(api.toggle).toHaveBeenCalledTimes(1);
    });

    it("keeps current state after a real write failure and permits an explicit retry", async () => {
        api.toggle.mockRejectedValueOnce(new Error("SYNTHETIC_WRITE_UNAVAILABLE"));
        await openSchedules();
        choose(24);
        await waitFor(() => expect(api.toast).toHaveBeenCalledTimes(1));
        expect(interval()).toHaveValue(12);
        expect(api.list).toHaveBeenCalledTimes(1);
        expect(api.toast).toHaveBeenCalledWith(expect.objectContaining({ messageKey: "schedules.intervalFailed" }));
        choose(24);
        await waitFor(() => expect(api.toggle).toHaveBeenCalledTimes(2));
    });

    it("accepts the valid nullable interval ACK and uses the overview default", async () => {
        api.toggle.mockResolvedValueOnce({ ...a, schedule_interval_hours: null });
        api.list.mockResolvedValueOnce([a, b]).mockRejectedValueOnce(new Error("SYNTHETIC_READ_UNAVAILABLE"));
        await openSchedules();
        choose(24);
        await screen.findByRole("alert");
        expect(interval()).toHaveValue(24);
        expect(api.toast).not.toHaveBeenCalled();
        expect(api.toggle).toHaveBeenCalledTimes(1);
    });

    it.each([
        ["en", "Could not refresh schedules. Saved changes are kept.", "No active schedules"],
        ["it", "Impossibile aggiornare le pianificazioni. Le modifiche salvate sono conservate.", "Nessuna pianificazione attiva"],
    ])("shows the saved-state warning and read retry in the %s empty view", async (language, message, title) => {
        api.list.mockResolvedValueOnce([a]).mockRejectedValueOnce(new Error("SYNTHETIC_READ_UNAVAILABLE"));
        await openSchedules({ language });
        fireEvent.click(screen.getByRole("checkbox"));
        expect(await screen.findByRole("alert")).toHaveTextContent(message);
        expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
        expect(within(screen.getByRole("alert")).getByRole("button")).toBeEnabled();
    });
});
