import { MemoryRouter } from "react-router";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceHomePage } from "./WorkspaceHomePage";
import { careerProfile } from "../../test/fixtures";
import { renderWithI18n as render } from "../../test/renderWithI18n";
import { assertAccessible } from "../../test/accessibility";

const mocks = vi.hoisted(() => ({
    getProfile: vi.fn(),
    listResumes: vi.fn(),
    listApplications: vi.fn(),
    getSearchOverview: vi.fn(),
    getSearchStatuses: vi.fn(),
    refreshModel: vi.fn(),
    modelStatus: vi.fn(),
}));

vi.mock("../../services/career", () => ({
    CareerService: { getProfile: mocks.getProfile },
}));

vi.mock("../../services/resumes", () => ({
    ResumeService: { list: mocks.listResumes },
}));

vi.mock("../../services/applications", () => ({
    ApplicationService: { list: mocks.listApplications },
}));

vi.mock("../../services/search", () => ({
    SearchService: {
        getProfileOverview: mocks.getSearchOverview,
        getAllStatuses: mocks.getSearchStatuses,
    },
}));

vi.mock("../local-model/useLocalModelStatus", () => ({
    useLocalModelStatus: () => mocks.modelStatus(),
}));

vi.mock("../local-model/ModelManager", () => ({
    ModelManager: ({ status }) => <div data-testid="model-manager">{status.ready ? "model ready" : "model setup"}</div>,
}));

vi.mock("./DataRecoveryPanel", () => ({
    DataRecoveryPanel: () => null,
}));

function apiError(status) {
    return Object.assign(new Error(`HTTP ${status}`), { status });
}

function searchOverview({
    totalProfiles = 0,
    totalSuccessfulRuns = 0,
    completedAt = null,
    jobsFound = null,
    items = [],
} = {}) {
    return {
        items,
        page: 1,
        page_size: 100,
        total_pages: totalProfiles > 0 ? Math.ceil(totalProfiles / 100) : 0,
        aggregate: {
            total_profiles: totalProfiles,
            total_successful_runs: totalSuccessfulRuns,
            latest_successful_completed_at: completedAt,
            latest_successful_jobs_found: jobsFound,
        },
    };
}

function renderHome({ withHeading = false } = {}) {
    return render(
        <MemoryRouter>
            {withHeading ? <main><h1>Home</h1><WorkspaceHomePage /></main> : <WorkspaceHomePage />}
        </MemoryRouter>,
    );
}

describe("WorkspaceHomePage progressive setup", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mocks.getProfile.mockRejectedValue(apiError(404));
        mocks.listResumes.mockResolvedValue([]);
        mocks.listApplications.mockResolvedValue([]);
        mocks.getSearchOverview.mockResolvedValue(searchOverview());
        mocks.getSearchStatuses.mockResolvedValue({});
        mocks.modelStatus.mockReturnValue({
            status: {
                loading: false,
                available: true,
                ready: false,
                configured_model: "",
                installed_models: [],
                error_code: null,
            },
            refresh: mocks.refreshModel,
        });
    });

    it("shows four precise first-use actions backed by empty API state", async () => {
        renderHome();

        expect(await screen.findByRole("heading", { name: "Confirm your career facts" })).toBeInTheDocument();
        expect(screen.getAllByRole("listitem")).toHaveLength(4);
        expect(screen.getByRole("link", { name: /Complete Career Vault/i })).toHaveAttribute("href", "/profile");
        expect(screen.getByRole("link", { name: /Set up model/i })).toHaveAttribute("href", "#home-model-setup");
        expect(screen.getByRole("link", { name: /Start first search/i })).toHaveAttribute("href", "/new");
        expect(screen.getByRole("link", { name: /Open application pipeline/i })).toHaveAttribute("href", "/applications");
    });

    it("replaces the checklist with one useful action once every milestone is verified", async () => {
        mocks.getProfile.mockResolvedValue(careerProfile());
        mocks.listApplications.mockResolvedValue([{
            id: "application-1",
            title: "Backend Engineer",
            company: "Local Co",
            current_stage: "saved",
            updated_at: "2026-07-20T12:00:00Z",
        }]);
        mocks.getSearchOverview.mockResolvedValue(searchOverview({ totalProfiles: 1 }));
        mocks.getSearchStatuses.mockResolvedValue({
            7: { state: "done", jobs_found: 3, finished_at: "2026-07-20T11:00:00Z" },
        });
        mocks.modelStatus.mockReturnValue({
            status: {
                loading: false,
                available: true,
                ready: true,
                configured_model: "qwen3-1.7b-q8",
                installed_models: ["qwen3-1.7b-q8"],
                error_code: null,
            },
            refresh: mocks.refreshModel,
        });

        renderHome();

        expect(await screen.findByRole("heading", { name: "The essentials are in place" })).toBeInTheDocument();
        expect(screen.queryByRole("list")).not.toBeInTheDocument();
        expect(screen.getByRole("link", { name: /Review applications/i })).toHaveAttribute("href", "/applications");
    });

    it("keeps the first search complete from its durable receipt after runtime status expires", async () => {
        mocks.getSearchOverview.mockResolvedValue(searchOverview({
            totalProfiles: 145,
            totalSuccessfulRuns: 3,
            completedAt: "2026-07-20T11:00:00Z",
            jobsFound: 8,
            items: [{ id: 145 }],
        }));
        mocks.getSearchStatuses.mockRejectedValue(apiError(503));

        renderHome();

        expect(await screen.findByRole("heading", { name: "First search completed" })).toBeInTheDocument();
        expect(screen.getByText(/Completed searches: 3/)).toHaveTextContent("20 Jul 2026");
        expect(screen.getByText(/Completed searches: 3/)).toHaveTextContent("8 jobs");
        expect(screen.queryByRole("heading", { name: "Search status unavailable" })).not.toBeInTheDocument();
    });

    it("uses runtime completion only as a compatibility fallback when profiles fail", async () => {
        mocks.getSearchOverview.mockRejectedValue(apiError(503));
        mocks.getSearchStatuses.mockResolvedValue({
            7: { state: "done", jobs_found: 5, finished_at: "2026-07-20T11:00:00Z" },
        });

        renderHome();

        expect(await screen.findByRole("heading", { name: "First search completed" })).toBeInTheDocument();
        expect(screen.getByText("The latest verified run found 5 jobs.")).toBeInTheDocument();
    });

    it("marks unavailable API sources without inventing zero progress", async () => {
        mocks.getProfile.mockRejectedValue(apiError(503));
        mocks.listApplications.mockRejectedValue(apiError(503));
        mocks.getSearchOverview.mockResolvedValue(searchOverview());
        mocks.getSearchStatuses.mockRejectedValue(apiError(503));

        renderHome();

        expect(await screen.findByRole("heading", { name: "Career Vault status unavailable" })).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: "Search status unavailable" })).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: "Application status unavailable" })).toBeInTheDocument();
        expect(screen.queryByRole("heading", { name: "First search completed" })).not.toBeInTheDocument();
        expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
    });

    it("does not claim completion when a saved search outlives retained status", async () => {
        mocks.getSearchOverview.mockResolvedValue(searchOverview({ totalProfiles: 1 }));
        mocks.getSearchStatuses.mockResolvedValue({});

        renderHome();

        expect(await screen.findByRole("heading", { name: "Review your search activity" })).toBeInTheDocument();
        expect(screen.getByRole("link", { name: /Review search history/i })).toHaveAttribute("href", "/history");
        expect(screen.queryByRole("heading", { name: "First search completed" })).not.toBeInTheDocument();
    });

    it("retries unavailable home sources and passes an automated accessibility check", async () => {
        const user = userEvent.setup();
        mocks.getProfile.mockRejectedValueOnce(apiError(503)).mockRejectedValueOnce(apiError(404));
        const { container } = renderHome({ withHeading: true });

        await user.click((await screen.findAllByRole("button", { name: /Check again/i }))[0]);
        await waitFor(() => expect(mocks.getProfile).toHaveBeenCalledTimes(2));
        expect(await screen.findByRole("heading", { name: "Confirm your career facts" })).toBeInTheDocument();
        await assertAccessible(container);
    });
});
