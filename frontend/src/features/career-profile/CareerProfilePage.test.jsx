import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { ApiError } from "../../lib/client";
import { careerProfile, EXPERIENCE_ID } from "../../test/fixtures";
import { renderWithItalian } from "../../test/renderWithI18n";
import { assertAccessible } from "../../test/accessibility";
import { CareerProfilePage } from "./CareerProfilePage";

const getProfile = vi.fn();
const saveProfile = vi.fn();
const listResumeVersions = vi.fn();
const showToast = vi.fn();
const uploadSource = vi.fn();

vi.mock("../../services/career", () => ({ CareerService: { getProfile: (...args) => getProfile(...args), saveProfile: (...args) => saveProfile(...args), uploadSource: (...args) => uploadSource(...args) } }));
vi.mock("../../services/resumes", () => ({ ResumeService: { listVersions: (...args) => listResumeVersions(...args) } }));
vi.mock("../../context/AuthContext", () => ({ useAuth: () => ({ user: "mira" }) }));
vi.mock("../../context/ToastContext", () => ({ useToast: () => ({ showToast }) }));

function render(ui, { route = "/profile", ...options } = {}) {
    return renderWithItalian(<MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>, options);
}

const importedSource = {
    id: "source-1",
    original_name: "career.txt",
    extracted_characters: 20,
    sha256: "a".repeat(64),
    text_preview: "Competenze: Python",
    candidates: [{
        candidate_id: "b".repeat(64),
        fact_type: "skill",
        payload: { name: "Python", level: "working" },
        source_locator: "paragraph:1:skill:1",
        confidence: 0.82,
        excerpt: "Competenze: Python",
    }],
};

describe("CareerProfilePage", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        getProfile.mockResolvedValue(careerProfile());
        listResumeVersions.mockResolvedValue([
            { id: "resume-version-1", draft_id: "resume-1", draft_title: "CV Staff", semantic_version: "1.0.0", published_at: "2026-07-01T10:00:00Z" },
        ]);
        uploadSource.mockResolvedValue(importedSource);
        saveProfile.mockImplementation(async (payload) => careerProfile({ revision: payload.expected_revision + 1, headline: payload.headline }));
    });

    it("bootstraps a new local Vault before the first CV import and keeps facts unconfirmed", async () => {
        const user = userEvent.setup();
        getProfile.mockRejectedValueOnce(new ApiError("Career profile not initialized", { status: 404 }));
        saveProfile.mockResolvedValueOnce(careerProfile({
            revision: 1,
            display_name: "mira",
            headline: "",
            summary: "",
            facts: [],
            goals: [],
            analysis: null,
        }));

        const { container } = render(<CareerProfilePage />, { route: "/profile?start=import" });
        expect(await screen.findByRole("heading", { name: "Parti dal CV che hai già" })).toBeInTheDocument();

        await user.upload(screen.getByLabelText("Documento sorgente"), new File(["career"], "career.txt", { type: "text/plain" }));
        await user.click(screen.getByRole("button", { name: "Importa localmente" }));
        expect(await screen.findByText("Candidati da revisionare")).toBeInTheDocument();

        expect(saveProfile).toHaveBeenCalledWith(expect.objectContaining({
            expected_revision: 0,
            display_name: "mira",
            facts: [],
        }));
        expect(saveProfile.mock.invocationCallOrder[0]).toBeLessThan(uploadSource.mock.invocationCallOrder[0]);

        await user.click(screen.getByRole("checkbox", { name: /Python/ }));
        await user.click(screen.getByRole("button", { name: "Accetta 1 candidati selezionati" }));
        expect(screen.getByRole("combobox", { name: "Stato" })).toHaveValue("imported");

        await user.click(screen.getByRole("button", { name: "Controlla i fatti importati" }));
        await waitFor(() => expect(screen.getByRole("heading", { name: /Fatti professionali/ })).toHaveFocus());
        await assertAccessible(container);
    });

    it("does not upload a CV when the initial profile write fails", async () => {
        const user = userEvent.setup();
        getProfile.mockRejectedValueOnce(new ApiError("Career profile not initialized", { status: 404 }));
        saveProfile.mockRejectedValueOnce(new ApiError("Local storage is full", { status: 507 }));

        render(<CareerProfilePage />, { route: "/profile?start=import" });
        await user.upload(await screen.findByLabelText("Documento sorgente"), new File(["career"], "career.txt", { type: "text/plain" }));
        await user.click(screen.getByRole("button", { name: "Importa localmente" }));

        expect(await screen.findByText("Local storage is full")).toBeInTheDocument();
        expect(uploadSource).not.toHaveBeenCalled();
        expect(screen.getByText("career.txt")).toBeInTheDocument();
    });

    it("imports directly when the Career Vault already exists", async () => {
        const user = userEvent.setup();
        render(<CareerProfilePage />, { route: "/profile?start=import" });

        await user.upload(await screen.findByLabelText("Documento sorgente"), new File(["career"], "career.txt", { type: "text/plain" }));
        await user.click(screen.getByRole("button", { name: "Importa localmente" }));

        await screen.findByText("Candidati da revisionare");
        expect(saveProfile).not.toHaveBeenCalled();
        expect(uploadSource).toHaveBeenCalledTimes(1);
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

    it("routes provider installation and network consent to Provider Studio", async () => {
        render(<CareerProfilePage />);

        const link = await screen.findByRole("link", { name: "Apri Studio provider" });
        expect(link).toHaveAttribute("href", "/providers");
        expect(screen.queryByRole("checkbox", { name: /Job-Room/ })).not.toBeInTheDocument();
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
