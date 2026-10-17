import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { application } from "../../test/fixtures";
import { assertAccessible } from "../../test/accessibility";
import { renderWithItalian as render } from "../../test/renderWithI18n";
import { ApplicationsPage } from "./ApplicationsPage";

const list = vi.fn();
const agenda = vi.fn();
const get = vi.fn();
const create = vi.fn();
const showToast = vi.fn();
const readiness = vi.fn();
const addEvent = vi.fn();
const resumeList = vi.fn();
const resumeGet = vi.fn();
const campaignList = vi.fn();
const campaignPreview = vi.fn();
const campaignImport = vi.fn();
const campaignContext = vi.fn();
const campaignDownload = vi.fn();

vi.mock("../../services/applications", () => ({ ApplicationService: { list: (...args) => list(...args), agenda: (...args) => agenda(...args), get: (...args) => get(...args), create: (...args) => create(...args), readiness: (...args) => readiness(...args), downloadReadiness: vi.fn(), updatePreparation: vi.fn(), addEvent: (...args) => addEvent(...args), getDossierDraft: vi.fn().mockResolvedValue(null) } }));
vi.mock("../../services/resumes", () => ({ ResumeService: { list: (...args) => resumeList(...args), get: (...args) => resumeGet(...args) } }));
vi.mock("../../services/campaigns", () => ({ CampaignService: {
    list: (...args) => campaignList(...args),
    preview: (...args) => campaignPreview(...args),
    importArchive: (...args) => campaignImport(...args),
    applicationContext: (...args) => campaignContext(...args),
    downloadArtifact: (...args) => campaignDownload(...args),
} }));
vi.mock("../../context/ToastContext", () => ({ useToast: () => ({ showToast }) }));

function summary(id, title, company = "Local Co") {
    return {
        id,
        title,
        company,
        location: "Zurigo",
        current_stage: "saved",
        updated_at: "2026-01-02T10:00:00Z",
    };
}

function deferred() {
    let resolve;
    const promise = new Promise((resolver) => { resolve = resolver; });
    return { promise, resolve };
}

describe("ApplicationsPage", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        document.body.style.overflow = "";
        list.mockResolvedValue([]);
        agenda.mockResolvedValue({
            generated_at: "2026-07-23T10:00:00Z",
            local_day_end: "2026-07-23T22:00:00Z",
            horizon_end: "2026-07-30T10:00:00Z",
            active_count: 0,
            visible_count: 0,
            later_count: 0,
            truncated_count: 0,
            items: [],
        });
        get.mockResolvedValue(application());
        create.mockResolvedValue(application());
        addEvent.mockResolvedValue(application());
        resumeList.mockResolvedValue([]);
        resumeGet.mockResolvedValue({ title: "ATS Resume", versions: [] });
        campaignList.mockResolvedValue([]);
        campaignContext.mockRejectedValue({ status: 404 });
        campaignPreview.mockResolvedValue({
            fingerprint: "a".repeat(64), suggested_name: "Legacy application campaign",
            suggested_profile_name: "Fictional Candidate", tracker_rows: 4,
            dossier_count: 3, matched_count: 2, tracker_only_count: 2,
            dossier_only_count: 1, logical_application_count: 5, artifact_count: 16,
            expanded_bytes: 12345, status_counts: { Applied: 1 },
            credential_rows_omitted: 0, warnings: [], sample: [], requires_profile_name: false,
        });
        campaignImport.mockResolvedValue({
            campaign_id: "11111111-1111-4111-8111-111111111111",
            created: true,
            application_count: 5,
        });
        campaignDownload.mockResolvedValue({ blob: new Blob(["artifact"]), filename: "cv.pdf" });
        readiness.mockResolvedValue({
            status: "blocked", completeness_score: 10, blocker_count: 8, warning_count: 0,
            fingerprint: "a".repeat(64), checks: [],
        });
    });

    it("creates a local job snapshot from a deep-linked job id", async () => {
        const user = userEvent.setup();
        render(<MemoryRouter initialEntries={["/applications?jobId=42"]}><ApplicationsPage /></MemoryRouter>);
        const submit = await screen.findByRole("button", { name: "Crea candidatura" });
        await user.type(screen.getByLabelText("Nota iniziale"), "Contattata tramite referral");
        await user.click(submit);

        await waitFor(() => expect(create).toHaveBeenCalledWith({ job_id: 42, initial_stage: "saved", resume_version_id: null, note: "Contattata tramite referral" }));
        expect(await screen.findByText("Snapshot locale")).toBeInTheDocument();
        expect(showToast).toHaveBeenCalledWith({ messageKey: "applications.added" }, "success");

        await user.keyboard("{Escape}");
        await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
        expect(screen.getByRole("button", { name: "Aggiungi candidatura" })).toHaveFocus();
    });

    it("opens a deep-linked application record and restores focus to its card", async () => {
        const user = userEvent.setup();
        const applicationId = "44444444-4444-4444-8444-444444444444";
        list.mockResolvedValue([summary(applicationId, "Backend Engineer")]);

        render(<MemoryRouter initialEntries={[`/applications?applicationId=${applicationId}`]}><ApplicationsPage /></MemoryRouter>);

        const trigger = await screen.findByRole("button", { name: /Backend Engineer/i });
        const dialog = await screen.findByRole("dialog", { name: "Backend Engineer" });
        expect(get).toHaveBeenCalledWith(applicationId, expect.objectContaining({ signal: expect.any(AbortSignal) }));
        expect(screen.queryByRole("button", { name: "Crea candidatura" })).not.toBeInTheDocument();
        await assertAccessible(dialog);

        await user.keyboard("{Escape}");

        await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
        expect(trigger).toHaveFocus();
        expect(get).toHaveBeenCalledTimes(1);
    });

    it("creates a manual snapshot when no discovered job id exists", async () => {
        const user = userEvent.setup();
        render(<MemoryRouter initialEntries={["/applications"]}><ApplicationsPage /></MemoryRouter>);
        await user.click(await screen.findByRole("button", { name: "Aggiungi la prima candidatura" }));
        await user.type(screen.getByLabelText("Titolo"), "Security Engineer");
        await user.type(screen.getByLabelText("Azienda"), "Local Systems");
        await user.type(screen.getByLabelText("Località"), "Zurich");
        await user.click(screen.getByRole("button", { name: "Crea candidatura" }));

        await waitFor(() => expect(create).toHaveBeenCalledWith({
            manual_job: {
                title: "Security Engineer", company: "Local Systems", location: "Zurich",
                external_url: null, description: null,
            },
            initial_stage: "saved", resume_version_id: null, note: null,
        }));
    });

    it("aborts the application list request on unmount", async () => {
        list.mockImplementationOnce(() => new Promise(() => {}));
        const { unmount } = render(<MemoryRouter initialEntries={["/applications"]}><ApplicationsPage /></MemoryRouter>);
        await waitFor(() => expect(list).toHaveBeenCalledTimes(1));
        const [{ signal }] = list.mock.calls[0];

        unmount();

        expect(signal.aborted).toBe(true);
    });

    it("distinguishes a resume metadata failure from an empty library and retries it", async () => {
        const user = userEvent.setup();
        resumeList
            .mockRejectedValueOnce(new Error("offline"))
            .mockResolvedValueOnce([{ id: "draft-1" }]);
        resumeGet.mockResolvedValue({
            title: "ATS Resume",
            versions: [{ id: "version-1", semantic_version: "1.0.0", selected_fact_ids: [] }],
        });
        render(<MemoryRouter initialEntries={["/applications"]}><ApplicationsPage /></MemoryRouter>);

        expect(await screen.findByRole("alert")).toHaveTextContent(
            "Non è stato possibile caricare le versioni CV pubblicate"
        );
        expect(screen.queryByText(/Non ci sono ancora versioni CV pubblicate/i)).not.toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: "Riprova a caricare i CV" }));
        await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
        await user.click(screen.getByRole("button", { name: "Aggiungi la prima candidatura" }));
        expect(screen.getByRole("option", { name: "ATS Resume · v1.0.0" })).toBeInTheDocument();
        expect(resumeList).toHaveBeenCalledTimes(2);
    });

    it("keeps the full board usable when the daily agenda fails", async () => {
        agenda.mockRejectedValue(new Error("agenda unavailable"));
        list.mockResolvedValue([
            summary("44444444-4444-4444-8444-444444444444", "Backend Engineer"),
        ]);

        render(<MemoryRouter initialEntries={["/applications"]}><ApplicationsPage /></MemoryRouter>);

        expect(await screen.findByRole("alert")).toHaveTextContent(
            "La board completa resta disponibile"
        );
        expect(screen.getByRole("button", { name: /Backend Engineer/i })).toBeEnabled();
    });

    it("opens an accessible modal, contains keyboard focus and restores the page", async () => {
        const user = userEvent.setup();
        const item = summary("44444444-4444-4444-8444-444444444444", "Backend Engineer");
        list.mockResolvedValue([item]);
        readiness.mockResolvedValue({
            status: "blocked", completeness_score: 80, blocker_count: 1, warning_count: 0,
            fingerprint: "b".repeat(64),
            checks: [{
                id: "role_description", status: "blocker", points_awarded: 0, points_available: 14,
                evidence: [{ key: "description_characters", value: "0" }],
                action: "capture_role_description",
            }],
        });
        document.body.style.overflow = "scroll";
        const { container } = render(<MemoryRouter initialEntries={["/applications"]}><ApplicationsPage /></MemoryRouter>);
        const trigger = await screen.findByRole("button", { name: /Backend Engineer/i });

        await user.click(trigger);

        const dialog = await screen.findByRole("dialog", { name: "Backend Engineer" });
        const background = container.querySelector(".applications-workspace__background");
        const close = within(dialog).getByRole("button", { name: "Chiudi dettagli candidatura" });
        expect(dialog).toHaveAttribute("aria-modal", "true");
        expect(dialog).toHaveAttribute("aria-describedby", "application-detail-summary");
        expect(close).toHaveFocus();
        expect(background).toHaveAttribute("inert");
        expect(background).toHaveAttribute("aria-hidden", "true");
        expect(container).toHaveAttribute("inert");
        expect(document.body.style.overflow).toBe("hidden");
        await assertAccessible(dialog);

        await user.tab({ shift: true });
        expect(within(dialog).getByRole("button", { name: "Registra evento" })).toHaveFocus();

        await user.click(within(dialog).getByRole("button", { name: /Modifica pacchetto/i }));
        const editorTitle = within(dialog).getByRole("heading", { name: "Modifica pacchetto candidatura" });
        expect(editorTitle).toHaveFocus();
        await user.tab();
        expect(dialog).toContainElement(document.activeElement);

        await user.keyboard("{Escape}");

        await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
        expect(background).not.toHaveAttribute("inert");
        expect(background).not.toHaveAttribute("aria-hidden");
        expect(container).not.toHaveAttribute("inert");
        expect(document.body.style.overflow).toBe("scroll");
        expect(trigger).toHaveFocus();
    });

    it("keeps only the latest application detail request", async () => {
        const user = userEvent.setup();
        const first = deferred();
        const second = deferred();
        const firstId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
        const secondId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
        list.mockResolvedValue([
            summary(firstId, "Platform Engineer"),
            summary(secondId, "ML Engineer", "Research Systems"),
        ]);
        get.mockImplementation((id) => id === firstId ? first.promise : second.promise);
        render(<MemoryRouter initialEntries={["/applications"]}><ApplicationsPage /></MemoryRouter>);

        await user.click(await screen.findByRole("button", { name: /Platform Engineer/i }));
        await user.click(screen.getByRole("button", { name: /ML Engineer/i }));
        expect(get.mock.calls[0][1].signal.aborted).toBe(true);

        second.resolve(application({
            id: secondId,
            job_snapshot: { title: "ML Engineer", company: "Research Systems", location: "Zurigo" },
        }));
        expect(await screen.findByRole("dialog", { name: "ML Engineer" })).toBeInTheDocument();

        first.resolve(application({
            id: firstId,
            job_snapshot: { title: "Platform Engineer", company: "Local Co", location: "Zurigo" },
        }));
        await waitFor(() => expect(screen.queryByRole("dialog", { name: "Platform Engineer" })).not.toBeInTheDocument());
        expect(screen.getByRole("dialog", { name: "ML Engineer" })).toBeInTheDocument();
    });

    it("keeps the dialog mounted and realigns the next stage after an update", async () => {
        const user = userEvent.setup();
        const applicationId = "44444444-4444-4444-8444-444444444444";
        const triggerSummary = summary(applicationId, "Backend Engineer");
        const saved = application();
        const preparing = application({ current_stage: "preparing", revision: 2 });
        const returnedToSaved = application({ current_stage: "saved", revision: 3 });
        list.mockResolvedValue([triggerSummary]);
        get.mockResolvedValue(saved);
        addEvent.mockResolvedValueOnce(preparing).mockResolvedValueOnce(returnedToSaved);
        render(<MemoryRouter initialEntries={["/applications"]}><ApplicationsPage /></MemoryRouter>);
        const trigger = await screen.findByRole("button", { name: /Backend Engineer/i });
        await user.click(trigger);
        const dialog = await screen.findByRole("dialog", { name: "Backend Engineer" });

        expect(within(dialog).getByLabelText("Nuova fase")).toHaveValue("preparing");
        await user.click(within(dialog).getByRole("button", { name: "Registra evento" }));
        await waitFor(() => expect(addEvent).toHaveBeenNthCalledWith(1, applicationId, expect.objectContaining({
            expected_revision: 1,
            event_type: "stage",
            stage: "preparing",
        })));
        expect(screen.getByRole("dialog", { name: "Backend Engineer" })).toBe(dialog);
        await waitFor(() => expect(within(dialog).getByLabelText("Nuova fase")).toHaveValue("saved"));

        await user.click(within(dialog).getByRole("button", { name: "Registra evento" }));
        await waitFor(() => expect(addEvent).toHaveBeenNthCalledWith(2, applicationId, expect.objectContaining({
            expected_revision: 2,
            event_type: "stage",
            stage: "saved",
        })));

        await user.keyboard("{Escape}");
        await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
        expect(trigger).toHaveFocus();
    });

    it("filters imported campaign summaries and shows their inert materials in application detail", async () => {
        const user = userEvent.setup();
        const importedId = "44444444-4444-4444-8444-444444444444";
        list.mockResolvedValue([
            {
                ...summary(importedId, "Backend Engineer", "Acme Corp"),
                current_stage: "applied",
                campaign_id: "11111111-1111-4111-8111-111111111111",
                source_application_id: "APP-001",
                campaign_priority: "High",
                campaign_platform: "LinkedIn",
                campaign_category: "Engineering",
            },
            summary("55555555-5555-4555-8555-555555555555", "Manual Designer"),
        ]);
        campaignList.mockResolvedValue([{
            id: "11111111-1111-4111-8111-111111111111",
            name: "Spring search",
            summary: { application_count: 5 },
        }]);
        get.mockResolvedValue(application({
            id: importedId,
            current_stage: "applied",
            job_snapshot: { title: "Backend Engineer", company: "Acme Corp" },
        }));
        campaignContext.mockResolvedValue({
            campaign_id: "11111111-1111-4111-8111-111111111111",
            campaign_name: "Spring search",
            application_id: importedId,
            source_application_id: "APP-001",
            tracker_record: { Notes: "Historical <b>plain text</b>" },
            provenance: { sources: ["tracker", "dossier"] },
            artifact_groups: {},
        });

        render(<MemoryRouter initialEntries={["/applications"]}><ApplicationsPage /></MemoryRouter>);
        expect(await screen.findByRole("button", { name: /Backend Engineer/i })).toBeVisible();
        expect(screen.getByRole("button", { name: /Manual Designer/i })).toBeVisible();

        await user.selectOptions(screen.getByLabelText("Campagna"), "11111111-1111-4111-8111-111111111111");
        expect(screen.getByRole("button", { name: /Backend Engineer/i })).toBeVisible();
        expect(screen.queryByRole("button", { name: /Manual Designer/i })).toBeNull();
        expect(screen.getByText("Attive").nextElementSibling).toHaveTextContent("1");
        await user.type(screen.getByLabelText("Cerca nelle candidature"), "LinkedIn");
        expect(screen.getByRole("button", { name: /Backend Engineer/i })).toBeVisible();
        await user.clear(screen.getByLabelText("Cerca nelle candidature"));
        await user.type(screen.getByLabelText("Cerca nelle candidature"), "Engineering");
        expect(screen.getByRole("button", { name: /Backend Engineer/i })).toBeVisible();
        await user.clear(screen.getByLabelText("Cerca nelle candidature"));
        await user.type(screen.getByLabelText("Cerca nelle candidature"), "missing");
        expect(screen.queryByRole("button", { name: /Backend Engineer/i })).toBeNull();
        expect(screen.getByText("Attive").nextElementSibling).toHaveTextContent("0");
        await user.clear(screen.getByLabelText("Cerca nelle candidature"));
        await user.click(screen.getByRole("button", { name: /Backend Engineer/i }));

        const dialog = await screen.findByRole("dialog", { name: "Backend Engineer" });
        expect(await within(dialog).findByRole("heading", { name: "Materiali campagna" })).toBeVisible();
        expect(within(dialog).getByText("Historical <b>plain text</b>")).toBeVisible();
        expect(dialog.querySelector("b")).toBeNull();
    });

    it("refreshes campaigns and the board after a confirmed import", async () => {
        const user = userEvent.setup();
        list.mockResolvedValue([]);
        render(<MemoryRouter initialEntries={["/applications"]}><ApplicationsPage /></MemoryRouter>);
        await screen.findByRole("button", { name: "Scegli archivio campagna" });
        await user.upload(
            screen.getByLabelText("Archivio ZIP della campagna"),
            new File(["PK"], "campaign.zip", { type: "application/zip" }),
        );
        await screen.findByRole("heading", { name: "Anteprima campagna" });
        await user.click(screen.getByRole("button", { name: /Importa 5 candidature/ }));

        await waitFor(() => expect(campaignImport).toHaveBeenCalledTimes(1));
        await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
        expect(campaignList).toHaveBeenCalledTimes(2);
        expect(showToast).toHaveBeenCalledWith(
            { messageKey: "applications.campaignImported", values: { count: 5 } },
            "success",
        );
    });
    it.each(["closed", "other", "same-newer"])("keeps current selection after a delayed update to a previous detail (%s)", async (target) => {
        const user = userEvent.setup();
        const pending = deferred();
        const firstId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
        const secondId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
        const first = application({ id: firstId, job_snapshot: { title: "First application", company: "Local Co" } });
        const second = application({ id: secondId, job_snapshot: { title: "Second application", company: "Local Co" } });
        let firstReads = 0;
        list.mockResolvedValue([summary(firstId, "First application"), summary(secondId, "Second application")]);
        get.mockImplementation(async (id) => id === secondId ? second : { ...first, revision: ++firstReads === 1 ? 1 : 3 });
        addEvent.mockReset().mockReturnValueOnce(pending.promise).mockResolvedValueOnce({ ...first, revision: 4 });
        render(<MemoryRouter initialEntries={["/applications"]}><ApplicationsPage /></MemoryRouter>);
        await user.click(await screen.findByRole("button", { name: /First application/i }));
        await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Registra evento" }));
        await waitFor(() => expect(addEvent).toHaveBeenCalledTimes(1));
        await user.keyboard("{Escape}");
        await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
        if (target !== "closed") {
            await user.click(screen.getByRole("button", { name: target === "other" ? /Second application/i : /First application/i }));
            await screen.findByRole("dialog", { name: target === "other" ? "Second application" : "First application" });
        }
        await act(async () => { pending.resolve({ ...first, revision: 2, current_stage: "preparing" }); await pending.promise; });
        if (target === "closed") {
            expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
        } else if (target === "other") {
            expect(screen.getByRole("dialog", { name: "Second application" })).toBeInTheDocument();
        } else {
            await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Registra evento" }));
            expect(addEvent).toHaveBeenLastCalledWith(firstId, expect.objectContaining({ expected_revision: 3 }));
        }
    });
    it("keeps a confirmed detail update when refreshing the board fails, and retries a failed write", async () => {
        const user = userEvent.setup();
        const first = application({ revision: 1 });
        const updated = { ...first, revision: 2, current_stage: "preparing" };
        list.mockReset().mockResolvedValueOnce([summary(first.id, first.job_snapshot.title)]).mockRejectedValue(new Error("Board unavailable"));
        get.mockResolvedValue(first);
        addEvent.mockReset().mockRejectedValueOnce(new Error("Write unavailable")).mockResolvedValue(updated);
        render(<MemoryRouter initialEntries={["/applications"]}><ApplicationsPage /></MemoryRouter>);
        await user.click(await screen.findByRole("button", { name: new RegExp(first.job_snapshot.title) }));
        const dialog = screen.getByRole("dialog");
        await user.click(within(dialog).getByRole("button", { name: "Registra evento" }));
        expect(await within(dialog).findByText("Write unavailable")).toHaveAttribute("role", "alert");
        await user.click(within(dialog).getByRole("button", { name: "Registra evento" }));
        await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
        expect(screen.getByRole("dialog")).toBe(dialog);
        expect(within(dialog).queryByText("Write unavailable")).not.toBeInTheDocument();
        expect(screen.getByText("Board unavailable")).toBeInTheDocument();
        await user.click(within(dialog).getByRole("button", { name: "Registra evento" }));
        expect(addEvent.mock.calls.map(([, payload]) => payload.expected_revision)).toEqual([1, 1, 2]);
        await user.keyboard("{Escape}");
        const board = document.querySelector(".application-board");
        expect(within(board).getByRole("button", { name: new RegExp(first.job_snapshot.title) }).closest("section"))
            .toHaveTextContent("Preparazione");
    });

    it("ignores a detail acknowledgement after the workspace unmounts", async () => {
        const user = userEvent.setup();
        const first = application();
        const pending = deferred();
        list.mockReset().mockResolvedValue([summary(first.id, first.job_snapshot.title)]);
        get.mockResolvedValue(first);
        addEvent.mockReset().mockReturnValue(pending.promise);
        const { unmount } = render(<MemoryRouter initialEntries={["/applications"]}><ApplicationsPage /></MemoryRouter>);
        await user.click(await screen.findByRole("button", { name: new RegExp(first.job_snapshot.title) }));
        await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Registra evento" }));
        unmount();
        await act(async () => { pending.resolve({ ...first, revision: 2 }); await pending.promise; });
        expect(list).toHaveBeenCalledTimes(1);
        expect(showToast).not.toHaveBeenCalled();
    });
    it("cancels a pending deep-linked detail when closing the current detail", async () => {
        const user = userEvent.setup();
        const first = application({ id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" });
        const second = application({ id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb" });
        const pending = deferred();
        list.mockReset().mockResolvedValue([summary(first.id, first.job_snapshot.title)]);
        get.mockReset().mockImplementation((id) => id === first.id ? Promise.resolve(first) : pending.promise);
        const router = createMemoryRouter([{ path: "/applications", element: <ApplicationsPage /> }], { initialEntries: ["/applications"] });
        render(<RouterProvider router={router} />);
        await user.click(await screen.findByRole("button", { name: new RegExp(first.job_snapshot.title) }));
        await screen.findByRole("dialog");
        await act(async () => router.navigate(`/applications?applicationId=${second.id}`));
        await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
        const signal = get.mock.calls[1][1].signal;
        await user.keyboard("{Escape}");
        await act(async () => { pending.resolve(second); await pending.promise; });
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
        expect(signal.aborted).toBe(true);
    });

    it.each(["other-detail", "closed-form"])("does not move selection after a delayed creation (%s)", async (target) => {
        const user = userEvent.setup();
        const created = application({ job_snapshot: { title: "Created application", company: "Local Co" } });
        const second = application({ id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", job_snapshot: { title: "Second application", company: "Local Co" } });
        const pending = deferred();
        list.mockReset().mockResolvedValue([summary(second.id, "Second application")]);
        get.mockResolvedValue(second);
        create.mockReset().mockReturnValue(pending.promise);
        render(<MemoryRouter initialEntries={["/applications?jobId=42"]}><ApplicationsPage /></MemoryRouter>);
        await user.click(await screen.findByRole("button", { name: "Crea candidatura" }));
        await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
        if (target === "other-detail") {
            await user.click(screen.getByRole("button", { name: /Second application/i }));
            await screen.findByRole("dialog", { name: "Second application" });
        } else await user.click(screen.getByRole("button", { name: "Chiudi", exact: true }));
        await act(async () => { pending.resolve(created); await pending.promise; });
        await waitFor(() => expect(showToast).toHaveBeenCalledWith({ messageKey: "applications.added" }, "success"));
        if (target === "other-detail") expect(screen.getByRole("dialog", { name: "Second application" })).toBeInTheDocument();
        else expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    it("preserves a reopened creation form and its newer draft after an old creation acknowledges", async () => {
        const user = userEvent.setup();
        const pending = deferred();
        create.mockReset().mockReturnValue(pending.promise);
        list.mockReset().mockResolvedValue([]);
        render(<MemoryRouter initialEntries={["/applications?jobId=42"]}><ApplicationsPage /></MemoryRouter>);
        const submit = await screen.findByRole("button", { name: "Crea candidatura" });
        await user.type(screen.getByLabelText("Nota iniziale"), "Submitted note");
        await user.click(submit);
        await user.click(screen.getByRole("button", { name: "Chiudi", exact: true }));
        await user.click(screen.getByRole("button", { name: "Aggiungi candidatura", exact: true }));
        await user.clear(screen.getByLabelText("Nota iniziale"));
        await user.type(screen.getByLabelText("Nota iniziale"), "New draft after reopening");
        await act(async () => { pending.resolve(application()); await pending.promise; });
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
        expect(screen.getByLabelText("Nota iniziale")).toHaveValue("New draft after reopening");
        expect(screen.getByRole("button", { name: "Crea candidatura" })).toBeEnabled();
        expect(showToast).toHaveBeenCalledWith({ messageKey: "applications.added" }, "success");
    });
});
