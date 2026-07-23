import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { assertAccessible } from "../../test/accessibility";
import { renderWithItalian as render } from "../../test/renderWithI18n";
import { ApplicationAgenda } from "./ApplicationAgenda";

const agenda = vi.fn();

vi.mock("../../services/applications", () => ({
    ApplicationService: { agenda: (...args) => agenda(...args) },
}));

function response(overrides = {}) {
    return {
        generated_at: "2026-07-23T10:00:00Z",
        local_day_end: "2026-07-23T22:00:00Z",
        horizon_end: "2026-07-30T10:00:00Z",
        active_count: 3,
        visible_count: 2,
        later_count: 1,
        truncated_count: 0,
        items: [
            {
                application_id: "11111111-1111-4111-8111-111111111111",
                application_revision: 2,
                title: "Platform Engineer",
                company: "Local Systems",
                current_stage: "applied",
                latest_event_at: "2026-07-22T10:00:00Z",
                state: "overdue",
                next_action: {
                    id: "task-one",
                    title: "Send follow-up",
                    due_at: "2026-07-22T10:00:00Z",
                    priority: "high",
                },
            },
            {
                application_id: "22222222-2222-4222-8222-222222222222",
                application_revision: 1,
                title: "ML Engineer",
                company: "Private Research",
                current_stage: "saved",
                latest_event_at: "2026-07-20T10:00:00Z",
                state: "needs_action",
                next_action: null,
            },
        ],
        ...overrides,
    };
}

describe("ApplicationAgenda", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        agenda.mockResolvedValue(response());
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it("renders a private ordered queue and opens the selected application", async () => {
        const user = userEvent.setup();
        const onOpen = vi.fn();
        const { container } = render(<ApplicationAgenda onOpen={onOpen} />);

        expect(await screen.findByRole("heading", { name: "Prossime azioni" })).toBeInTheDocument();
        const region = screen.getByRole("region", { name: "Prossime azioni" });
        expect(region).toHaveAttribute("aria-describedby", "application-agenda-description");
        expect(screen.getByText(/Una coda privata e deterministica/)).toBeVisible();
        expect(screen.getByText("Scaduta")).toBeInTheDocument();
        expect(screen.getByText("Azione mancante")).toBeInTheDocument();
        expect(screen.getByText("Send follow-up")).toBeInTheDocument();
        expect(screen.getByText("Oltre l’orizzonte di 7 giorni: 1.")).toBeInTheDocument();

        const trigger = screen.getByRole("button", {
            name: "Apri Platform Engineer presso Local Systems",
        });
        await user.click(trigger);
        expect(onOpen).toHaveBeenCalledWith(
            "11111111-1111-4111-8111-111111111111",
            trigger,
        );
        await assertAccessible(container);
    });

    it("reports a local failure and retries without hiding surrounding content", async () => {
        const user = userEvent.setup();
        agenda
            .mockRejectedValueOnce(new Error("local read failed"))
            .mockResolvedValueOnce(response({ active_count: 0, visible_count: 0, later_count: 0, items: [] }));
        render(<ApplicationAgenda onOpen={vi.fn()} />);

        expect(await screen.findByRole("alert")).toHaveTextContent(
            "La board completa resta disponibile"
        );
        await user.click(screen.getByRole("button", { name: "Riprova la coda" }));

        expect(await screen.findByText("Niente richiede attenzione")).toBeInTheDocument();
        await waitFor(() => expect(agenda).toHaveBeenCalledTimes(2));
    });

    it("aborts the agenda read on unmount", async () => {
        agenda.mockImplementationOnce(() => new Promise(() => {}));
        const { unmount } = render(<ApplicationAgenda onOpen={vi.fn()} />);
        await waitFor(() => expect(agenda).toHaveBeenCalledTimes(1));
        const [, { signal }] = agenda.mock.calls[0];

        unmount();

        expect(signal.aborted).toBe(true);
    });

    it("refreshes when the window regains focus or the document becomes visible", async () => {
        render(<ApplicationAgenda onOpen={vi.fn()} />);
        await screen.findByRole("heading", { name: "Prossime azioni" });
        expect(agenda).toHaveBeenCalledTimes(1);

        act(() => window.dispatchEvent(new Event("focus")));
        await waitFor(() => expect(agenda).toHaveBeenCalledTimes(2));

        Object.defineProperty(document, "visibilityState", {
            configurable: true,
            value: "visible",
        });
        act(() => document.dispatchEvent(new Event("visibilitychange")));
        await waitFor(() => expect(agenda).toHaveBeenCalledTimes(3));
        expect(agenda.mock.calls[1][1].signal.aborted).toBe(true);
    });

    it("refreshes at the next deadline and clears its timer on unmount", async () => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date("2026-07-23T10:00:00Z"));
        agenda
            .mockResolvedValueOnce(response({
                generated_at: "2026-07-23T10:00:00Z",
                local_day_end: "2026-07-23T22:00:00Z",
                items: [{
                    ...response().items[0],
                    next_action: {
                        ...response().items[0].next_action,
                        due_at: "2026-07-23T10:15:00Z",
                    },
                }],
                active_count: 1,
                visible_count: 1,
                later_count: 0,
            }))
            .mockResolvedValueOnce(response({
                generated_at: "2026-07-23T10:15:00Z",
                local_day_end: "2026-07-23T22:00:00Z",
                active_count: 0,
                visible_count: 0,
                later_count: 0,
                items: [],
            }));
        const view = render(<ApplicationAgenda onOpen={vi.fn()} />);
        await act(async () => {});
        expect(agenda).toHaveBeenCalledTimes(1);
        expect(vi.getTimerCount()).toBe(1);

        await act(async () => {
            vi.advanceTimersByTime(15 * 60 * 1000);
        });
        expect(agenda).toHaveBeenCalledTimes(2);

        view.unmount();
        expect(vi.getTimerCount()).toBe(0);
    });
});
