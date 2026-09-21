import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router";

import { AgentWorkService } from "../../services/agentWork";
import { AutomationService } from "../../services/automation";
import { ApplicationService } from "../../services/applications";
import { ResumeService } from "../../services/resumes";
import { assertAccessible } from "../../test/accessibility";
import { renderWithI18n } from "../../test/renderWithI18n";
import { AgentWorkPage } from "./AgentWorkPage";

vi.mock("../../services/agentWork", () => ({ AgentWorkService: {
    listWork: vi.fn(), createWork: vi.fn(), getWork: vi.fn(), cancelWork: vi.fn(),
    rejectWork: vi.fn(), acceptWork: vi.fn(),
} }));
vi.mock("../../services/automation", () => ({ AutomationService: { listGrants: vi.fn() } }));
vi.mock("../../services/applications", () => ({ ApplicationService: { list: vi.fn() } }));
vi.mock("../../services/resumes", () => ({ ResumeService: { list: vi.fn() } }));

const REQUEST_A = "550e8400-e29b-41d4-a716-446655440000";
const REQUEST_B = "550e8400-e29b-41d4-a716-446655440001";
const GRANT_ID = "550e8400-e29b-41d4-a716-446655440010";
const FACT_ID = "550e8400-e29b-41d4-a716-446655440020";
const DIGEST = "a".repeat(64);
const REVISIONS = { profile: 4, job: 7, application: null, resume: null, dossier: null };

const activeGrant = {
    id: GRANT_ID,
    label: "Codex workspace",
    scopes: ["context:read", "proposals:write"],
    expires_at: "2030-01-01T00:00:00Z",
    revoked_at: null,
};

function work(overrides = {}) {
    return {
        id: REQUEST_A,
        work_kind: "discover",
        state: "queued",
        revision: 1,
        instruction: "Find senior backend positions in Zurich",
        bound_grant_id: GRANT_ID,
        target_job_id: null,
        target_application_id: null,
        target_resume_id: null,
        preset_id: null,
        preset_version: null,
        locale: null,
        input_digest: DIGEST,
        expires_at: "2026-09-14T10:00:00Z",
        created_at: "2026-09-13T10:00:00Z",
        updated_at: "2026-09-13T10:00:00Z",
        error_code: null,
        ...overrides,
    };
}

function detail(request, proposal = null) {
    return {
        ...request,
        input_revisions: REVISIONS,
        selected_fact_ids: null,
        proposal,
        accepted_receipt: null,
    };
}

const dimensions = ["role", "requirements", "language", "location", "contract", "freshness"];
const gates = dimensions.map((dimension, index) => ({
    dimension,
    status: index === 3 ? "hold" : "eligible",
    reason: index === 3 ? "Commute duration needs confirmation" : `${dimension} requirement supported`,
    fact_ids: [FACT_ID],
    quote_references: [`${dimension} requirement from advert`],
    unknowns: index === 3 ? ["Exact commute time"] : [],
}));
const scores = {
    role: { score: 90, explanation: "Role evidence" },
    requirements: { score: 86, explanation: "Requirements evidence" },
    language: { score: 89, explanation: "Language evidence" },
    location: { score: 70, explanation: "Location evidence" },
    contract: { score: 95, explanation: "Contract evidence" },
    freshness: { score: 98, explanation: "Fresh listing" },
    overall_score: 88,
};

function analyzeProposal(overrides = {}) {
    return {
        id: "proposal-a",
        request_id: REQUEST_A,
        submitting_grant_id: GRANT_ID,
        idempotency_key: "proposal-a",
        payload_digest: "b".repeat(64),
        contract_version: 1,
        client_label: "Codex",
        model_label: "gpt-5.3-codex-spark",
        payload: {
            contract_version: 1,
            kind: "analyze",
            gates,
            scores,
            claims: [{ claim_text: "AWS delivery is supported", fact_ids: [FACT_ID], quote_text: "AWS production experience" }],
            recommendation: "strong_fit",
        },
        review_required: true,
        created_at: "2026-09-13T10:05:00Z",
        ...overrides,
    };
}

function listPage(items, returnedCount = items.length, offset = 0, limit = 25) {
    return { items, offset, limit, returned_count: returnedCount };
}

function renderPage(initialEntries = ["/agent-work"]) {
    const router = createMemoryRouter([
        { path: "/agent-work", element: <AgentWorkPage /> },
        { path: "/agent-access", element: <p>Agent access route</p> },
        { path: "/applications", element: <p>Application workspace route</p> },
    ], { initialEntries });
    return { ...renderWithI18n(<RouterProvider router={router} />), router };
}

function deferred() {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
}

describe("AgentWorkPage serialized API integration", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        AutomationService.listGrants.mockResolvedValue([activeGrant]);
        ApplicationService.list.mockResolvedValue([]);
        ResumeService.list.mockResolvedValue([]);
        AgentWorkService.listWork.mockResolvedValue(listPage([]));
        Object.defineProperty(navigator, "clipboard", {
            configurable: true,
            value: { writeText: vi.fn().mockResolvedValue(undefined) },
        });
    });

    it("renders truthful external disclosure and an accessible empty queue", async () => {
        const { container } = renderPage();
        await screen.findByText("No work requests");
        expect(screen.getByText(/may send the selected context to its model provider/i)).toBeInTheDocument();
        expect(AgentWorkService.listWork).toHaveBeenCalledWith(expect.objectContaining({
            offset: 0, limit: 25, state: undefined, signal: expect.any(AbortSignal),
        }));
        await assertAccessible(container);
    });

    it("opens a queued request with a private prompt and isolates the page behind the modal", async () => {
        const user = userEvent.setup();
        const clipboardWrite = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
        const queued = work();
        AgentWorkService.listWork.mockResolvedValue(listPage([queued]));
        AgentWorkService.getWork.mockResolvedValue(detail(queued));
        const { container } = renderPage();
        await screen.findByText(queued.instruction);
        await user.click(screen.getByRole("button", { name: "View details" }));
        const dialog = await screen.findByRole("dialog");
        expect(container.inert).toBe(true);
        const prompt = within(dialog).getByText(/Please process CareerOS agent work request/);
        expect(prompt).toHaveTextContent("get_work_context");
        expect(prompt).not.toHaveTextContent(queued.instruction);
        await user.click(within(dialog).getByRole("button", { name: "Copy prompt" }));
        expect(clipboardWrite).toHaveBeenCalledWith(expect.stringContaining(REQUEST_A));
        await user.click(within(dialog).getAllByRole("button", { name: "Close" })[0]);
        expect(container.inert).not.toBe(true);
    });

    it("creates a request with normative wire names and protects the in-flight submission", async () => {
        const user = userEvent.setup();
        const created = work({ instruction: "Find remote TypeScript roles" });
        AgentWorkService.createWork.mockResolvedValue(created);
        AgentWorkService.getWork.mockResolvedValue(detail(created));
        renderPage();
        await screen.findByText("No work requests");
        await user.click(screen.getAllByRole("button", { name: "New request" })[0]);
        const dialog = await screen.findByRole("dialog", { name: /Create work request/i });
        await user.type(within(dialog).getByRole("textbox", { name: /Instructions/ }), created.instruction);
        await user.click(within(dialog).getByRole("button", { name: "Create request" }));
        await waitFor(() => expect(AgentWorkService.createWork).toHaveBeenCalledWith({
            work_kind: "discover",
            grant_id: GRANT_ID,
            instruction: created.instruction,
        }, { signal: expect.any(AbortSignal) }));
    });

    it("shows all analysis fields and accepts with the complete frozen target revisions", async () => {
        const user = userEvent.setup();
        const returned = work({ work_kind: "analyze", state: "returned", revision: 2, target_job_id: 42, instruction: "Analyze cloud architect" });
        AgentWorkService.listWork.mockResolvedValue(listPage([returned]));
        AgentWorkService.getWork.mockResolvedValue(detail(returned, analyzeProposal()));
        AgentWorkService.acceptWork.mockResolvedValue({ request_id: REQUEST_A, proposal_id: "proposal-a", accepted_at: "2026-09-13T10:10:00Z" });
        const { container } = renderPage();
        await screen.findByText(returned.instruction);
        await user.click(screen.getByRole("button", { name: "Review proposal" }));
        const dialog = await screen.findByRole("dialog");
        expect(within(dialog).getByText(/Codex \(gpt-5.3-codex-spark\)/)).toBeInTheDocument();
        expect(within(dialog).getByText("Strong fit")).toBeInTheDocument();
        expect(within(dialog).getByText("AWS delivery is supported")).toBeInTheDocument();
        expect(within(dialog).getByText("88")).toBeInTheDocument();
        expect(within(dialog).getAllByText("Eligible")).toHaveLength(5);
        expect(within(dialog).getByText("Exact commute time")).toBeInTheDocument();
        await user.click(within(dialog).getByRole("button", { name: "Accept proposal" }));
        await waitFor(() => expect(AgentWorkService.acceptWork).toHaveBeenCalledWith(REQUEST_A, {
            expected_revision: 2,
            expected_target_revisions: REVISIONS,
        }));
        expect(await within(dialog).findByText("Proposal accepted")).toBeInTheDocument();
        await assertAccessible(container);
    });

    it("opens the targeted application after accepted materials", async () => {
        const user = userEvent.setup();
        const applicationId = "550e8400-e29b-41d4-a716-446655440030";
        const accepted = work({
            work_kind: "materials",
            state: "accepted",
            revision: 3,
            target_application_id: applicationId,
            target_resume_id: "550e8400-e29b-41d4-a716-446655440031",
            accepted_receipt: { request_id: REQUEST_A, proposal_id: "proposal-a" },
        });
        AgentWorkService.listWork.mockResolvedValue(listPage([accepted]));
        AgentWorkService.getWork.mockResolvedValue({
            ...detail(accepted),
            accepted_receipt: accepted.accepted_receipt,
        });
        renderPage();
        await screen.findByText(accepted.instruction);
        await user.click(screen.getByRole("button", { name: "View details" }));
        const link = await screen.findByRole("link", { name: /Open accepted application materials/i });
        expect(link).toHaveAttribute("href", `/applications?applicationId=${applicationId}`);
        await user.click(link);
        expect(await screen.findByText("Application workspace route")).toBeInTheDocument();
    });

    it("shows every applied material field and creates a targeted materials request", async () => {
        const user = userEvent.setup();
        const applicationId = "550e8400-e29b-41d4-a716-446655440030";
        const resumeId = "550e8400-e29b-41d4-a716-446655440031";
        ApplicationService.list.mockResolvedValue([{ id: applicationId, title: "Platform Engineer", company: "Example AG" }]);
        ResumeService.list.mockResolvedValue([{ id: resumeId, title: "Platform CV" }]);
        const returned = work({
            work_kind: "materials", state: "returned", revision: 3,
            target_application_id: applicationId, target_resume_id: resumeId,
        });
        const materialProposal = analyzeProposal({
            payload: {
                contract_version: 1,
                kind: "materials",
                preset_id: "swiss-software-en",
                preset_version: 1,
                locale: "en",
                cv_selected_fact_ids: [FACT_ID],
                cv_cited_overrides: [{ id: "cv-1", text: "Led a verified migration.", fact_ids: [FACT_ID] }],
                cover_letter: [{ id: "letter-1", text: "I delivered the cited platform migration.", fact_ids: [FACT_ID] }],
                email: {
                    mode: "motivational",
                    subject: "Application: Platform Engineer",
                    body: [{ id: "email-1", text: "Please find my reviewed application attached.", fact_ids: [FACT_ID] }],
                    attachment_names: ["resume.pdf", "cover-letter.pdf"],
                },
                questions_answers: [{ id: "answer-1", question: "Why this role?", text: "The platform scope matches my verified work.", fact_ids: [FACT_ID] }],
                requirements_to_evidence: [{ requirement: "Platform migration", quote_text: "Lead a platform migration", fact_ids: [FACT_ID] }],
                review_notes: "Confirm the recipient before export.",
            },
        });
        AgentWorkService.listWork.mockResolvedValue(listPage([returned]));
        AgentWorkService.getWork.mockResolvedValue(detail(returned, materialProposal));
        renderPage();
        await screen.findByText(returned.instruction);
        await user.click(screen.getByRole("button", { name: "Review proposal" }));
        let dialog = await screen.findByRole("dialog");
        for (const text of [
            "Led a verified migration.",
            "I delivered the cited platform migration.",
            "Application: Platform Engineer",
            "Please find my reviewed application attached.",
            "Why this role?",
            "Platform migration",
            "Confirm the recipient before export.",
        ]) expect(within(dialog).getByText(text)).toBeInTheDocument();
        await user.click(within(dialog).getAllByRole("button", { name: "Close" })[0]);

        await user.click(screen.getByRole("button", { name: "New request" }));
        dialog = await screen.findByRole("dialog", { name: /Create work request/i });
        await user.click(within(dialog).getByRole("radio", { name: /Materials/ }));
        await user.selectOptions(await within(dialog).findByRole("combobox", { name: "Application" }), applicationId);
        await user.selectOptions(within(dialog).getByRole("combobox", { name: "CV draft" }), resumeId);
        await user.type(within(dialog).getByRole("textbox", { name: /Instructions/ }), "Draft reviewed application materials");
        AgentWorkService.createWork.mockResolvedValue(work({ id: REQUEST_B, work_kind: "materials", instruction: "Draft reviewed application materials" }));
        AgentWorkService.getWork.mockResolvedValue(detail(work({ id: REQUEST_B, work_kind: "materials", instruction: "Draft reviewed application materials" })));
        await user.click(within(dialog).getByRole("button", { name: "Create request" }));
        await waitFor(() => expect(AgentWorkService.createWork).toHaveBeenCalledWith({
            work_kind: "materials",
            grant_id: GRANT_ID,
            instruction: "Draft reviewed application materials",
            target_application_id: applicationId,
            target_resume_id: resumeId,
        }, { signal: expect.any(AbortSignal) }));
    });

    it("uses the strict rejection CAS body without an unsupported reason field", async () => {
        const user = userEvent.setup();
        const returned = work({ work_kind: "analyze", state: "returned", revision: 2 });
        AgentWorkService.listWork.mockResolvedValue(listPage([returned]));
        AgentWorkService.getWork.mockResolvedValue(detail(returned, analyzeProposal()));
        AgentWorkService.rejectWork.mockResolvedValue({ ...returned, state: "rejected", revision: 3 });
        renderPage();
        await screen.findByText(returned.instruction);
        await user.click(screen.getByRole("button", { name: "Review proposal" }));
        const dialog = await screen.findByRole("dialog");
        await user.click(within(dialog).getByRole("button", { name: "Reject proposal" }));
        expect(within(dialog).queryByRole("textbox")).not.toBeInTheDocument();
        await user.click(within(dialog).getByRole("button", { name: "Confirm rejection" }));
        await waitFor(() => expect(AgentWorkService.rejectWork).toHaveBeenCalledWith(REQUEST_A, { expected_revision: 2 }));
    });

    it("renders every discovery listing's scores, gates, source and safe URL", async () => {
        const user = userEvent.setup();
        const returned = work({ state: "returned" });
        const proposal = analyzeProposal({
            payload: {
                contract_version: 1,
                kind: "discover",
                listings: [{
                    title: "Senior Backend Engineer",
                    company: "Swiss FinTech AG",
                    location: "Zürich",
                    external_url: "https://jobs.example.ch/backend-1",
                    source_text: "We need a Python engineer.",
                    observed_at: "2026-09-13T09:30:00Z",
                    source_platform: "company-site",
                    gates,
                    scores,
                }],
            },
        });
        AgentWorkService.listWork.mockResolvedValue(listPage([returned]));
        AgentWorkService.getWork.mockResolvedValue(detail(returned, proposal));
        renderPage();
        await screen.findByText(returned.instruction);
        await user.click(screen.getByRole("button", { name: "Review proposal" }));
        const dialog = await screen.findByRole("dialog");
        expect(within(dialog).getByText("Senior Backend Engineer")).toBeInTheDocument();
        expect(within(dialog).getByText("Swiss FinTech AG")).toBeInTheDocument();
        expect(within(dialog).getByText("88")).toBeInTheDocument();
        expect(within(dialog).getByRole("link", { name: "View original advert" })).toHaveAttribute("href", "https://jobs.example.ch/backend-1");
        await user.click(within(dialog).getByText("Show captured advert text"));
        expect(within(dialog).getByText("We need a Python engineer.")).toBeInTheDocument();
    });

    it("blocks acceptance of legacy payload aliases", async () => {
        const user = userEvent.setup();
        const returned = work({ state: "returned" });
        AgentWorkService.listWork.mockResolvedValue(listPage([returned]));
        AgentWorkService.getWork.mockResolvedValue(detail(returned, {
            ...analyzeProposal(), payload: undefined, result: { kind: "discover", vacancies: [] },
        }));
        renderPage();
        await screen.findByText(returned.instruction);
        await user.click(screen.getByRole("button", { name: "Review proposal" }));
        const dialog = await screen.findByRole("dialog");
        expect(within(dialog).getByText("This proposal cannot be reviewed")).toBeInTheDocument();
        expect(within(dialog).getByRole("button", { name: "Accept proposal" })).toBeDisabled();
    });

    it("loads older pages and sends state filters to the server", async () => {
        const user = userEvent.setup();
        const first = Array.from({ length: 25 }, (_, index) => work({ id: `${REQUEST_A.slice(0, -2)}${String(index).padStart(2, "0")}`, instruction: `Page one ${index}` }));
        const older = work({ id: REQUEST_B, instruction: "Oldest reachable request" });
        AgentWorkService.listWork
            .mockResolvedValueOnce(listPage(first, 25))
            .mockResolvedValueOnce(listPage([older], 1, 25))
            .mockResolvedValueOnce(listPage([], 0));
        renderPage();
        await screen.findByText("Page one 0");
        await user.click(screen.getByRole("button", { name: "Load older requests" }));
        expect(await screen.findByText("Oldest reachable request")).toBeInTheDocument();
        expect(AgentWorkService.listWork).toHaveBeenNthCalledWith(2, expect.objectContaining({ offset: 25, limit: 25 }));
        await user.click(screen.getByRole("tab", { name: "Returned" }));
        await waitFor(() => expect(AgentWorkService.listWork).toHaveBeenLastCalledWith(expect.objectContaining({ state: "returned", offset: 0 })));
    });

    it("ignores a late detail response after the user opens a different request", async () => {
        const user = userEvent.setup();
        const requestA = work({ instruction: "Request A", state: "returned" });
        const requestB = work({ id: REQUEST_B, instruction: "Request B", state: "returned" });
        const pendingA = deferred();
        const pendingB = deferred();
        AgentWorkService.listWork.mockResolvedValue(listPage([requestA, requestB]));
        AgentWorkService.getWork.mockImplementation((id) => (id === REQUEST_A ? pendingA.promise : pendingB.promise));
        renderPage();
        const cardA = (await screen.findByText("Request A")).closest("article");
        await user.click(within(cardA).getByRole("button", { name: "Review proposal" }));
        let dialog = await screen.findByRole("dialog");
        await user.click(within(dialog).getAllByRole("button", { name: "Close" })[0]);
        const cardB = screen.getByText("Request B").closest("article");
        await user.click(within(cardB).getByRole("button", { name: "Review proposal" }));
        pendingB.resolve(detail({ ...requestB, instruction: "Detailed B" }, analyzeProposal({ request_id: REQUEST_B, client_label: "Claude B" })));
        expect(await screen.findByRole("heading", { name: "Detailed B" })).toBeInTheDocument();
        pendingA.resolve(detail({ ...requestA, instruction: "Late A" }, analyzeProposal({ client_label: "Late A client" })));
        await waitFor(() => expect(screen.queryByText("Late A client")).not.toBeInTheDocument());
        dialog = screen.getByRole("dialog");
        expect(within(dialog).getByText(/Claude B/)).toBeInTheDocument();
    });

    it("shows grant-load failure and retries without pretending there are no grants", async () => {
        const user = userEvent.setup();
        AutomationService.listGrants
            .mockRejectedValueOnce(new Error("offline"))
            .mockResolvedValueOnce([activeGrant]);
        renderPage();
        await screen.findByText("No work requests");
        await user.click(screen.getAllByRole("button", { name: "New request" })[0]);
        const dialog = await screen.findByRole("dialog", { name: /Create work request/i });
        expect(await within(dialog).findByText("offline")).toBeInTheDocument();
        await user.click(within(dialog).getByRole("button", { name: "Try again" }));
        expect(await within(dialog).findByRole("combobox", { name: "Bound agent grant" })).toHaveValue(GRANT_ID);
    });
});
