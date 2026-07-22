import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { careerProfile, EXPERIENCE_ID } from "../../test/fixtures";
import { renderWithItalian as render } from "../../test/renderWithI18n";
import { assertAccessible } from "../../test/accessibility";
import { CareerProfilePage } from "./CareerProfilePage";

const getProfile = vi.fn();
const saveProfile = vi.fn();
const getJobSources = vi.fn();
const listResumeVersions = vi.fn();
const showToast = vi.fn();

vi.mock("../../services/career", () => ({ CareerService: { getProfile: (...args) => getProfile(...args), getJobSources: (...args) => getJobSources(...args), saveProfile: (...args) => saveProfile(...args), uploadSource: vi.fn() } }));
vi.mock("../../services/resumes", () => ({ ResumeService: { listVersions: (...args) => listResumeVersions(...args) } }));
vi.mock("../../context/AuthContext", () => ({ useAuth: () => ({ user: "mira" }) }));
vi.mock("../../context/ToastContext", () => ({ useToast: () => ({ showToast }) }));

describe("CareerProfilePage", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        getProfile.mockResolvedValue(careerProfile());
        getJobSources.mockResolvedValue([
            { key: "local_db", label: "Archivio locale", network: false, available: true, consented: true },
            { key: "job_room", label: "Job-Room", description: "Portale pubblico svizzero", network: true, available: true, consented: false },
        ]);
        listResumeVersions.mockResolvedValue([
            { id: "resume-version-1", draft_id: "resume-1", draft_title: "CV Staff", semantic_version: "1.0.0", published_at: "2026-07-01T10:00:00Z" },
        ]);
        saveProfile.mockImplementation(async (payload) => careerProfile({ revision: payload.expected_revision + 1, headline: payload.headline }));
    });

    it("saves an explicit optimistic revision and the edited profile", async () => {
        const user = userEvent.setup();
        render(<CareerProfilePage />);
        const headline = await screen.findByLabelText("Titolo professionale");
        await user.clear(headline);
        await user.type(headline, "Principal engineer");
        await user.click(screen.getByRole("button", { name: "Salva Career Vault" }));

        await waitFor(() => expect(saveProfile).toHaveBeenCalledTimes(1));
        expect(saveProfile.mock.calls[0][0]).toMatchObject({ expected_revision: 3, headline: "Principal engineer" });
        expect(saveProfile.mock.calls[0][0].facts[0]).not.toHaveProperty("created_at");
        expect(showToast).toHaveBeenCalledWith({ messageKey: "profile.savedToast" }, "success");
    });

    it("shows server-derived completeness, missing sections, conflicts and evidence state", async () => {
        render(<CareerProfilePage />);
        expect(await screen.findByText("68%")).toBeInTheDocument();
        expect(screen.getByText("Da completare")).toBeInTheDocument();
        expect(screen.getAllByText("Formazione").length).toBeGreaterThan(0);
        expect(screen.getByText("Controlli consigliati")).toBeInTheDocument();
        expect(screen.getByText("Due esperienze principali hanno date sovrapposte.")).toBeInTheDocument();
        expect(screen.getAllByText("Confermato da te")).toHaveLength(2);
    });

    it("edits detailed career history, compensation, gaps and milestones", async () => {
        render(<CareerProfilePage />);
        const experienceTitle = (await screen.findAllByText("Principal Engineer")).find((element) => element.tagName === "STRONG");
        fireEvent.click(experienceTitle);
        const industry = screen.getByLabelText("Settore");
        fireEvent.change(industry, { target: { value: "Privacy software" } });

        const minimum = screen.getByLabelText("Compenso minimo");
        fireEvent.change(minimum, { target: { value: "160000" } });
        fireEvent.click(screen.getByRole("button", { name: "Aggiungi gap" }));
        fireEvent.change(screen.getByLabelText("Competenza gap 1"), { target: { value: "Budgeting" } });
        fireEvent.click(screen.getByRole("button", { name: "Aggiungi traguardo" }));
        fireEvent.change(screen.getByLabelText("Traguardo 1"), { target: { value: "Guidare pianificazione annuale" } });
        fireEvent.click(screen.getByRole("button", { name: "Salva Career Vault" }));

        await waitFor(() => expect(saveProfile).toHaveBeenCalledTimes(1));
        const written = saveProfile.mock.calls[0][0];
        expect(written.facts.find((fact) => fact.id === EXPERIENCE_ID).payload).toMatchObject({
            industry: "Privacy software",
            employment_type: "permanent",
            team_size: 12,
        });
        expect(written.goals[0].payload.compensation.minimum).toBe(160000);
        expect(written.goals[0].payload.skill_gaps.at(-1).skill).toBe("Budgeting");
        expect(written.goals[0].payload.milestones.at(-1).title).toBe("Guidare pianificazione annuale");
    });

    it("links skill evidence, records dated achievements and tracks goal progress notes", async () => {
        render(<CareerProfilePage />);

        fireEvent.click(await screen.findByText("Python"));
        fireEvent.click(screen.getByLabelText("Evidenza Principal Engineer"));

        fireEvent.change(screen.getByLabelText("Nuova nota di avanzamento"), { target: { value: "Completato il primo colloquio esplorativo." } });
        fireEvent.click(screen.getByRole("button", { name: "Aggiungi nota di avanzamento" }));

        const typeSelect = screen.getByLabelText("Tipo di fatto da aggiungere");
        fireEvent.change(typeSelect, { target: { value: "achievement" } });
        fireEvent.click(typeSelect.parentElement.querySelector("button"));
        fireEvent.change(screen.getByLabelText("Risultato"), { target: { value: "Riduzione tempi di delivery" } });
        fireEvent.change(screen.getByLabelText("Data risultato"), { target: { value: "2026-06-30" } });
        fireEvent.change(screen.getByLabelText("Dettagli risultato · uno per riga"), { target: { value: "Lead time -40%\nZero regressioni critiche" } });
        fireEvent.click(screen.getByRole("button", { name: "Salva Career Vault" }));

        await waitFor(() => expect(saveProfile).toHaveBeenCalledTimes(1));
        const written = saveProfile.mock.calls[0][0];
        const skill = written.facts.find((fact) => fact.fact_type === "skill");
        const achievement = written.facts.find((fact) => fact.fact_type === "achievement");
        expect(skill.payload.evidence_fact_ids).toEqual([EXPERIENCE_ID]);
        expect(achievement.payload).toMatchObject({
            title: "Riduzione tempi di delivery",
            achieved_on: "2026-06-30",
            details: ["Lead time -40%", "Zero regressioni critiche"],
        });
        expect(written.goals[0].payload.progress_notes[0]).toMatchObject({
            text: "Completato il primo colloquio esplorativo.",
        });
        expect(Date.parse(written.goals[0].payload.progress_notes[0].recorded_at)).not.toBeNaN();
    });

    it("tracks measurable goal progress and evidence-linked actions", async () => {
        render(<CareerProfilePage />);
        fireEvent.change(await screen.findByLabelText("Avanzamento obiettivo %"), { target: { value: "45" } });
        fireEvent.click(screen.getByRole("button", { name: "Aggiungi azione" }));
        fireEvent.change(screen.getByLabelText("Azione 1"), { target: { value: "Pubblicare il case study" } });
        fireEvent.change(screen.getByLabelText("Tipo azione"), { target: { value: "portfolio" } });
        fireEvent.change(screen.getByLabelText("Stato azione"), { target: { value: "in_progress" } });
        fireEvent.click(screen.getByLabelText("Evidenza azione 1 Principal Engineer"));
        fireEvent.click(screen.getByRole("button", { name: "Salva Career Vault" }));

        await waitFor(() => expect(saveProfile).toHaveBeenCalledTimes(1));
        const goal = saveProfile.mock.calls[0][0].goals[0].payload;
        expect(goal.progress_percent).toBe(45);
        expect(goal.actions[0]).toMatchObject({
            title: "Pubblicare il case study",
            kind: "portfolio",
            status: "in_progress",
            linked_fact_ids: [EXPERIENCE_ID],
        });
    });

    it("persists explicit per-source network consent", async () => {
        const user = userEvent.setup();
        render(<CareerProfilePage />);

        await user.click(await screen.findByRole("checkbox", { name: /Job-Room/ }));
        await user.click(screen.getByRole("button", { name: "Salva Career Vault" }));

        await waitFor(() => expect(saveProfile).toHaveBeenCalledTimes(1));
        expect(saveProfile.mock.calls[0][0].preferences.job_source_consents).toEqual({
            job_room: true,
        });
    });

    it("links goal actions to learning activities and immutable resume versions", async () => {
        render(<CareerProfilePage />);
        await screen.findByText("Obiettivi di carriera");

        fireEvent.click(screen.getByRole("button", { name: "Aggiungi azione" }));
        fireEvent.change(screen.getByLabelText("Azione 1"), { target: { value: "Corso architettura" } });
        fireEvent.change(screen.getByLabelText("Tipo azione"), { target: { value: "learning" } });
        fireEvent.click(screen.getByRole("button", { name: "Aggiungi azione" }));
        fireEvent.change(screen.getByLabelText("Azione 2"), { target: { value: "Aggiorna CV" } });
        fireEvent.click(screen.getByLabelText("Attività formativa azione 2 Corso architettura"));
        fireEvent.click(screen.getByLabelText("Versione CV azione 2 CV Staff 1.0.0"));
        fireEvent.click(screen.getByRole("button", { name: "Salva Career Vault" }));

        await waitFor(() => expect(saveProfile).toHaveBeenCalledTimes(1));
        const actions = saveProfile.mock.calls[0][0].goals[0].payload.actions;
        expect(actions[1].linked_learning_activity_ids).toEqual([actions[0].id]);
        expect(actions[1].linked_resume_version_ids).toEqual(["resume-version-1"]);
    });

    it("passes the profile and goals accessibility and keyboard gate", async () => {
        const user = userEvent.setup();
        const { container } = render(<main><CareerProfilePage /></main>);
        await screen.findByLabelText("Nome visualizzato");

        await assertAccessible(container);
        const goalsSection = screen.getByRole("heading", { name: "Obiettivi di carriera" }).closest("section");
        const addGoal = within(goalsSection).getByRole("button", { name: "Aggiungi", exact: true });
        addGoal.focus();
        expect(addGoal).toHaveFocus();
        await user.keyboard("{Enter}");
        expect(screen.getByLabelText("Nome obiettivo 2")).toBeInTheDocument();
    });

    it("aborts the profile request on unmount", async () => {
        getProfile.mockImplementationOnce(() => new Promise(() => {}));
        const { unmount } = render(<CareerProfilePage />);
        await waitFor(() => expect(getProfile).toHaveBeenCalledTimes(1));
        const [{ signal }] = getProfile.mock.calls[0];

        unmount();

        expect(signal.aborted).toBe(true);
    });
});
