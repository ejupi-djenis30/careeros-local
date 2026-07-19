import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SearchService } from "../services/search";
import { History } from "./History";
import { Schedules } from "./Schedules";

const showToast = vi.fn();

vi.mock("../services/search", () => ({
    SearchService: {
        getProfiles: vi.fn(),
        toggleSchedule: vi.fn(),
    },
}));
vi.mock("../context/ToastContext", () => ({ useToast: () => ({ showToast }) }));
vi.mock("./HistoryCard", () => ({ HistoryCard: ({ profile }) => <div data-testid={`history-${profile.id}`} /> }));
vi.mock("./ScheduleCard", () => ({ ScheduleCard: ({ profile }) => <div data-testid={`schedule-${profile.id}`} /> }));
vi.mock("./ConfirmationDialog", () => ({ ConfirmationDialog: () => null }));

describe("profile list request lifecycle", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        SearchService.getProfiles.mockImplementation(() => new Promise(() => {}));
    });

    it("aborts the history request on unmount", async () => {
        const { unmount } = render(<History loadingProfileId={null} />);
        await waitFor(() => expect(SearchService.getProfiles).toHaveBeenCalledTimes(1));
        const [{ signal }] = SearchService.getProfiles.mock.calls[0];

        unmount();

        expect(signal.aborted).toBe(true);
        expect(showToast).not.toHaveBeenCalled();
    });

    it("aborts the schedules request on unmount", async () => {
        const { unmount } = render(<Schedules />);
        await waitFor(() => expect(SearchService.getProfiles).toHaveBeenCalledTimes(1));
        const [{ signal }] = SearchService.getProfiles.mock.calls[0];

        unmount();

        expect(signal.aborted).toBe(true);
        expect(showToast).not.toHaveBeenCalled();
    });

    it("renders history in reverse id order after a successful request", async () => {
        SearchService.getProfiles.mockResolvedValueOnce([{ id: 1 }, { id: 3 }, { id: 2 }]);
        render(<History loadingProfileId={null} />);

        await waitFor(() => expect(screen.getAllByTestId(/history-/)).toHaveLength(3));

        expect(screen.getAllByTestId(/history-/).map((element) => element.dataset.testid)).toEqual([
            "history-3",
            "history-2",
            "history-1",
        ]);
    });

    it("only renders enabled schedules after a successful request", async () => {
        SearchService.getProfiles.mockResolvedValueOnce([
            { id: 1, schedule_enabled: false },
            { id: 2, schedule_enabled: true },
        ]);
        render(<Schedules />);

        expect(await screen.findByTestId("schedule-2")).toBeInTheDocument();
        expect(screen.queryByTestId("schedule-1")).not.toBeInTheDocument();
    });

    it("recovers from a history request failure when retried", async () => {
        const user = userEvent.setup();
        const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
        SearchService.getProfiles
            .mockRejectedValueOnce(new Error("Unavailable"))
            .mockResolvedValueOnce([]);
        render(<History loadingProfileId={null} />);

        await user.click(await screen.findByRole("button", { name: "Try again" }));

        expect(await screen.findByText("No History")).toBeInTheDocument();
        expect(showToast).toHaveBeenCalledWith("Failed to load search history.");
        consoleSpy.mockRestore();
    });
});
