import { describe, expect, it } from "vitest";

import { nextAgendaRefreshDelay, nextLocalDayEnd } from "./agendaTime";

describe("agenda time boundaries", () => {
    it("uses the browser calendar to find the next local midnight", () => {
        const now = new Date(2026, 2, 29, 12, 34, 56, 789);
        const boundary = nextLocalDayEnd(now);

        expect(boundary.getFullYear()).toBe(now.getFullYear());
        expect(boundary.getMonth()).toBe(now.getMonth());
        expect(boundary.getDate()).toBe(now.getDate() + 1);
        expect(boundary.getHours()).toBe(0);
        expect(boundary.getMinutes()).toBe(0);
        expect(boundary.getSeconds()).toBe(0);
        expect(boundary.getMilliseconds()).toBe(0);
    });

    it("refreshes at the earliest future deadline or local midnight", () => {
        const now = new Date("2026-07-23T10:00:00Z");
        const data = {
            generated_at: "2026-07-23T09:59:59Z",
            local_day_end: "2026-07-23T22:00:00Z",
            items: [
                { next_action: { due_at: "2026-07-23T10:30:00Z" } },
                { next_action: { due_at: "2026-07-23T10:15:00Z" } },
            ],
        };

        expect(nextAgendaRefreshDelay(data, now)).toBe(15 * 60 * 1000);
    });

    it("requests an immediate refresh when a response boundary passed in transit", () => {
        const data = {
            generated_at: "2026-07-23T09:59:00Z",
            local_day_end: "2026-07-23T22:00:00Z",
            items: [{ next_action: { due_at: "2026-07-23T10:00:00Z" } }],
        };

        expect(
            nextAgendaRefreshDelay(data, new Date("2026-07-23T10:00:01Z")),
        ).toBe(0);
    });

    it("rejects invalid dates and ignores malformed response boundaries", () => {
        expect(() => nextLocalDayEnd("not-a-date")).toThrow(TypeError);
        expect(nextAgendaRefreshDelay({}, new Date())).toBeNull();
    });
});
