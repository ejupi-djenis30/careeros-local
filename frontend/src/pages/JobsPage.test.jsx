import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithI18n as render } from "../test/renderWithI18n";
import { JobsPage } from "./JobsPage";

const { jobTableMock, useJobsMock } = vi.hoisted(() => ({
    jobTableMock: vi.fn(),
    useJobsMock: vi.fn(),
}));

vi.mock("../context/AuthContext", () => ({
    useAuth: () => ({ logout: vi.fn() }),
}));

vi.mock("../hooks/useJobs", () => ({
    useJobs: (...args) => useJobsMock(...args),
}));

vi.mock("../components/JobTable", () => ({
    JobTable: (props) => {
        jobTableMock(props);
        return <div data-testid="job-table" />;
    },
}));

vi.mock("../components/FilterBar", () => ({
    FilterBar: () => <div data-testid="filter-bar" />,
}));

vi.mock("../components/ManualJobImporter", () => ({
    ManualJobImporter: () => <div data-testid="manual-importer" />,
}));

function jobsState(pagination) {
    return {
        jobs: [],
        pagination: {
            total: 12,
            avg_score: 76,
            page: 1,
            pages: 1,
            ...pagination,
        },
        setPagination: vi.fn(),
        filters: {},
        setFilters: vi.fn(),
        searchProfiles: [],
        fetchJobs: vi.fn(),
        dismissJob: vi.fn(),
        reactivateJob: vi.fn(),
        clearFilters: vi.fn(),
        isLoading: false,
        isRefreshing: false,
        fetchError: "",
    };
}

describe("JobsPage", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("uses the tracked application total and no longer wires a legacy toggle", () => {
        useJobsMock.mockReturnValue(jobsState({ total_tracked: 7, total_applied: 3 }));

        render(<JobsPage />);

        const trackedCard = screen.getByText("Tracked").closest(".glass-panel");
        expect(within(trackedCard).getByText("7")).toBeInTheDocument();
        expect(jobTableMock.mock.calls.at(-1)[0]).not.toHaveProperty("onToggleApplied");
        expect(jobTableMock.mock.calls.at(-1)[0]).not.toHaveProperty("isAppliedPending");
    });

    it("falls back to the legacy total while older backends are still in use", () => {
        useJobsMock.mockReturnValue(jobsState({ total_applied: 4 }));

        render(<JobsPage />);

        const trackedCard = screen.getByText("Tracked").closest(".glass-panel");
        expect(within(trackedCard).getByText("4")).toBeInTheDocument();
    });
});
