import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
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

vi.mock("../../services/applications", () => ({ ApplicationService: { list: (...args) => list(...args), agenda: (...args) => agenda(...args), get: (...args) => get(...args), create: (...args) => create(...args), readiness: (...args) => readiness(...args), downloadReadiness: vi.fn(), updatePreparation: vi.fn(), addEvent: (...args) => addEvent(...args) } }));
vi.mock("../../services/resumes", () => ({ ResumeService: { list: (...args) => resumeList(...args), get: (...args) => resumeGet(...args) } }));
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
});
