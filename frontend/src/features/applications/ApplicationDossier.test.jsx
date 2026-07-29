import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { application, careerProfile } from "../../test/fixtures";
import { assertAccessible } from "../../test/accessibility";
import { renderWithItalian as render } from "../../test/renderWithI18n";
import { ApplicationDossier } from "./ApplicationDossier";

const publishDossier = vi.fn();
const downloadDossier = vi.fn();
const getDossierDraft = vi.fn();
const saveDossierDraft = vi.fn();
const deleteDossierDraft = vi.fn();
const getProfile = vi.fn();

vi.mock("../../services/applications", () => ({ ApplicationService: {
    publishDossier: (...args) => publishDossier(...args),
    downloadDossier: (...args) => downloadDossier(...args),
    getDossierDraft: (...args) => getDossierDraft(...args),
    saveDossierDraft: (...args) => saveDossierDraft(...args),
    deleteDossierDraft: (...args) => deleteDossierDraft(...args),
} }));
vi.mock("../../services/career", () => ({ CareerService: {
    getProfile: (...args) => getProfile(...args),
} }));

describe("ApplicationDossier", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        getProfile.mockResolvedValue(careerProfile());
        getDossierDraft.mockResolvedValue(null);
        saveDossierDraft.mockImplementation((_id, data) => Promise.resolve({
            application_id: application().id,
            resume_version_id: data.resume_version_id,
            application_revision: data.expected_application_revision,
            revision: (data.expected_revision || 0) + 1,
            content: data.content,
            created_at: "2026-07-29T12:00:00Z",
            updated_at: "2026-07-29T12:00:00Z",
        }));
        deleteDossierDraft.mockResolvedValue(null);
        publishDossier.mockResolvedValue(application({ revision: 2 }));
    });

    it("publishes a requirement-to-confirmed-evidence dossier", async () => {
        const user = userEvent.setup();
        const profile = careerProfile();
        const fact = profile.facts[0];
        const onChanged = vi.fn();
        render(<ApplicationDossier
            application={application({ resume_version_id: "version-1", dossiers: [] })}
            resumeVersions={[{ id: "version-1", selected_fact_ids: [fact.id] }]}
            onChanged={onChanged}
        />);

        const evidence = await screen.findByRole("checkbox", { name: /Python.*requisito 1/i });
        await user.type(screen.getByLabelText("Requisito del ruolo 1"), "Build Python services");
        await user.click(evidence);
        await user.type(screen.getByLabelText("Lettera di presentazione"), "I build local systems.");
        await user.click(screen.getByRole("button", { name: "Pubblica versione dossier" }));

        await waitFor(() => expect(publishDossier).toHaveBeenCalledWith(application().id, {
            expected_revision: 1,
            expected_draft_revision: 1,
            cover_letter: "I build local systems.",
            answers: [],
            checklist: [],
            requirement_matrix: [{ requirement: "Build Python services", evidence_fact_ids: [fact.id] }],
        }));
        expect(onChanged).toHaveBeenCalledTimes(1);
    });

    it("publishes multiple requirements, answers and checklist items without dropping rows", async () => {
        const user = userEvent.setup();
        const profile = careerProfile();
        const fact = profile.facts[0];
        render(<ApplicationDossier
            application={application({ resume_version_id: "version-1", dossiers: [] })}
            resumeVersions={[{ id: "version-1", selected_fact_ids: [fact.id] }]}
            onChanged={vi.fn()}
        />);

        await screen.findByText(/Bozza pronta/);
        fireEvent.change(screen.getByLabelText("Requisito del ruolo 1"), {
            target: { value: "Build Python services" },
        });
        await user.click(await screen.findByRole("checkbox", { name: /Python.*requisito 1/i }));
        await user.click(screen.getByRole("button", { name: "Aggiungi requisito" }));
        fireEvent.change(screen.getByLabelText("Requisito del ruolo 2"), {
            target: { value: "Operate local systems" },
        });
        await user.click(screen.getByRole("checkbox", { name: /Python.*requisito 2/i }));

        fireEvent.change(screen.getByLabelText("Domanda della candidatura 1"), {
            target: { value: "Why this role?" },
        });
        fireEvent.change(screen.getByLabelText("La tua risposta 1"), {
            target: { value: "The scope matches my work." },
        });
        await user.click(screen.getByRole("button", { name: "Aggiungi risposta" }));
        fireEvent.change(screen.getByLabelText("Domanda della candidatura 2"), {
            target: { value: "When can you start?" },
        });
        fireEvent.change(screen.getByLabelText("La tua risposta 2"), {
            target: { value: "After my notice period." },
        });

        fireEvent.change(screen.getByLabelText("Voce della checklist 1"), {
            target: { value: "Resume reviewed" },
        });
        await user.click(screen.getByRole("checkbox", { name: "Completata" }));
        await user.click(screen.getByRole("button", { name: "Aggiungi voce checklist" }));
        fireEvent.change(screen.getByLabelText("Voce della checklist 2"), {
            target: { value: "References ready" },
        });
        await user.click(screen.getByRole("button", { name: "Pubblica versione dossier" }));

        await waitFor(() => expect(publishDossier).toHaveBeenCalledWith(application().id, {
            expected_revision: 1,
            expected_draft_revision: 1,
            cover_letter: null,
            answers: [
                { question: "Why this role?", answer: "The scope matches my work." },
                { question: "When can you start?", answer: "After my notice period." },
            ],
            checklist: [
                { label: "Resume reviewed", completed: true },
                { label: "References ready", completed: false },
            ],
            requirement_matrix: [
                { requirement: "Build Python services", evidence_fact_ids: [fact.id] },
                { requirement: "Operate local systems", evidence_fact_ids: [fact.id] },
            ],
        }));
    });

    it("reports a partial question and keeps every draft field intact", async () => {
        const user = userEvent.setup();
        const profile = careerProfile();
        const fact = profile.facts[0];
        render(<ApplicationDossier
            application={application({ resume_version_id: "version-1", dossiers: [] })}
            resumeVersions={[{ id: "version-1", selected_fact_ids: [fact.id] }]}
            onChanged={vi.fn()}
        />);

        await screen.findByText(/Bozza pronta/);
        await user.type(screen.getByLabelText("Requisito del ruolo 1"), "Build Python services");
        await user.click(await screen.findByRole("checkbox", { name: /Python.*requisito 1/i }));
        await user.type(screen.getByLabelText("Domanda della candidatura 1"), "Why this role?");
        await user.click(screen.getByRole("button", { name: "Pubblica versione dossier" }));

        expect(await screen.findByRole("alert")).toHaveTextContent(
            "Completa sia la domanda sia la risposta"
        );
        expect(screen.getByLabelText("Domanda della candidatura 1")).toHaveValue("Why this role?");
        expect(screen.getByLabelText("Requisito del ruolo 1")).toHaveValue("Build Python services");
        expect(publishDossier).not.toHaveBeenCalled();
    });

    it("provides explicit controls for removing repeated rows", async () => {
        const user = userEvent.setup();
        const profile = careerProfile();
        const fact = profile.facts[0];
        render(<ApplicationDossier
            application={application({ resume_version_id: "version-1", dossiers: [] })}
            resumeVersions={[{ id: "version-1", selected_fact_ids: [fact.id] }]}
            onChanged={vi.fn()}
        />);
        await screen.findByRole("checkbox", { name: /Python.*requisito 1/i });

        await user.click(screen.getByRole("button", { name: "Aggiungi requisito" }));
        await user.click(screen.getByRole("button", { name: "Aggiungi risposta" }));
        await user.click(screen.getByRole("button", { name: "Aggiungi voce checklist" }));
        await user.click(screen.getByRole("button", { name: "Rimuovi requisito 2" }));
        await user.click(screen.getByRole("button", { name: "Rimuovi risposta 2" }));
        await user.click(screen.getByRole("button", { name: "Rimuovi voce checklist 2" }));

        expect(screen.queryByLabelText("Requisito del ruolo 2")).not.toBeInTheDocument();
        expect(screen.queryByLabelText("Domanda della candidatura 2")).not.toBeInTheDocument();
        expect(screen.queryByLabelText("Voce della checklist 2")).not.toBeInTheDocument();
    });

    it("shows a profile load error and retries without pretending evidence is empty", async () => {
        const user = userEvent.setup();
        const profile = careerProfile();
        const fact = profile.facts[0];
        getProfile.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(profile);
        render(<ApplicationDossier
            application={application({ resume_version_id: "version-1", dossiers: [] })}
            resumeVersions={[{ id: "version-1", selected_fact_ids: [fact.id] }]}
            onChanged={vi.fn()}
        />);

        expect(await screen.findByRole("alert")).toHaveTextContent(
            "Non è stato possibile caricare le evidenze"
        );
        expect(screen.queryByText(/non contiene fatti confermati/i)).not.toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: "Riprova a caricare le evidenze" }));
        expect(await screen.findByRole("checkbox", { name: /Python.*requisito 1/i })).toBeEnabled();
        expect(getProfile).toHaveBeenCalledTimes(2);
    });

    it("reports linked resume metadata transport errors without showing zero evidence", async () => {
        const retry = vi.fn();
        render(<ApplicationDossier
            application={application({ resume_version_id: "version-1", dossiers: [] })}
            resumeVersions={[]}
            resumeMetadataStatus="error"
            onRetryResumeMetadata={retry}
            onChanged={vi.fn()}
        />);

        expect(await screen.findByRole("alert")).toHaveTextContent(
            "Non è stato possibile caricare i metadati del CV collegato"
        );
        expect(screen.queryByText(/non contiene fatti confermati/i)).not.toBeInTheDocument();
        await userEvent.click(screen.getByRole("button", { name: "Riprova a caricare il CV collegato" }));
        expect(retry).toHaveBeenCalledTimes(1);
    });

    it("removes only stale evidence when the linked resume changes", async () => {
        const user = userEvent.setup();
        const profile = careerProfile();
        const firstFact = profile.facts[0];
        const secondFact = profile.facts[1];
        const props = {
            resumeVersions: [
                { id: "version-1", selected_fact_ids: [firstFact.id] },
                { id: "version-2", selected_fact_ids: [secondFact.id] },
            ],
            onChanged: vi.fn(),
        };
        const view = render(<ApplicationDossier
            {...props}
            application={application({ resume_version_id: "version-1", dossiers: [] })}
        />);

        await screen.findByText(/Bozza pronta/);
        await user.type(screen.getByLabelText("Requisito del ruolo 1"), "Build local systems");
        await user.click(await screen.findByRole("checkbox", { name: /Python.*requisito 1/i }));
        view.rerender(<ApplicationDossier
            {...props}
            application={application({ resume_version_id: "version-2", dossiers: [] })}
        />);

        expect(await screen.findByText(/Sono stati rimossi 1 riferimenti/)).toBeInTheDocument();
        expect(screen.getByLabelText("Requisito del ruolo 1")).toHaveValue(
            "Build local systems"
        );
        expect(screen.queryByRole("checkbox", { name: /Python.*requisito 1/i })).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Pubblica versione dossier" })).toBeDisabled();
        await user.click(await screen.findByRole("checkbox", { name: /Principal Engineer.*requisito 1/i }));
        expect(screen.getByRole("button", { name: "Pubblica versione dossier" })).toBeEnabled();
    });

    it("restores the private SQLite-backed draft with its stable rows", async () => {
        const profile = careerProfile();
        const fact = profile.facts[0];
        getDossierDraft.mockResolvedValue({
            application_id: application().id,
            resume_version_id: "version-1",
            application_revision: 1,
            revision: 4,
            created_at: "2026-07-29T12:00:00Z",
            updated_at: "2026-07-29T12:05:00Z",
            content: {
                cover_letter: "Recovered from the local vault.",
                answers: [{
                    client_id: "answer-restored",
                    question: "Why here?",
                    answer: "The role is concrete.",
                }],
                checklist: [{
                    client_id: "check-restored",
                    label: "Portfolio reviewed",
                    completed: true,
                }],
                requirement_matrix: [{
                    client_id: "requirement-restored",
                    requirement: "Operate Python services",
                    evidence_fact_ids: [fact.id],
                }],
            },
        });

        render(<ApplicationDossier
            application={application({ resume_version_id: "version-1", dossiers: [] })}
            resumeVersions={[{ id: "version-1", selected_fact_ids: [fact.id] }]}
            onChanged={vi.fn()}
        />);

        expect(await screen.findByDisplayValue("Recovered from the local vault.")).toBeVisible();
        expect(screen.getByLabelText("Requisito del ruolo 1")).toHaveValue(
            "Operate Python services",
        );
        expect(screen.getByText("Bozza salvata su questo dispositivo.")).toBeVisible();
        expect(screen.getByRole("button", { name: "Elimina la bozza salvata" })).toBeEnabled();
    });

    it("autosaves to the API and never uses browser storage", async () => {
        const profile = careerProfile();
        const fact = profile.facts[0];
        const storageSpy = vi.spyOn(Storage.prototype, "setItem");
        const user = userEvent.setup();
        render(<ApplicationDossier
            application={application({ resume_version_id: "version-1", dossiers: [] })}
            resumeVersions={[{ id: "version-1", selected_fact_ids: [fact.id] }]}
            onChanged={vi.fn()}
        />);

        await screen.findByText(/Bozza pronta/);
        await user.type(
            screen.getByLabelText("Requisito del ruolo 1"),
            "Build local services",
        );

        await waitFor(() => expect(saveDossierDraft).toHaveBeenCalled(), { timeout: 2000 });
        expect(saveDossierDraft.mock.calls.at(-1)[1]).toMatchObject({
            expected_revision: null,
            expected_application_revision: 1,
            resume_version_id: "version-1",
            content: {
                requirement_matrix: [{
                    requirement: "Build local services",
                    evidence_fact_ids: [],
                }],
            },
        });
        expect(await screen.findByText("Bozza salvata su questo dispositivo.")).toBeVisible();
        expect(storageSpy).not.toHaveBeenCalled();
        storageSpy.mockRestore();
    });

    it("keeps every field visible when autosave fails and can retry", async () => {
        const profile = careerProfile();
        const fact = profile.facts[0];
        saveDossierDraft.mockRejectedValueOnce(new Error("database busy"));
        const user = userEvent.setup();
        render(<ApplicationDossier
            application={application({ resume_version_id: "version-1", dossiers: [] })}
            resumeVersions={[{ id: "version-1", selected_fact_ids: [fact.id] }]}
            onChanged={vi.fn()}
        />);

        await screen.findByText(/Bozza pronta/);
        const requirement = screen.getByLabelText("Requisito del ruolo 1");
        await user.type(requirement, "Keep this exact local text");
        expect(await screen.findByText(
            "Non è stato possibile salvare la bozza. Il modulo è rimasto invariato.",
            {},
            { timeout: 2000 },
        )).toBeVisible();
        expect(requirement).toHaveValue("Keep this exact local text");

        await user.click(screen.getByRole("button", { name: "Riprova il salvataggio" }));
        expect(await screen.findByText("Bozza salvata su questo dispositivo.")).toBeVisible();
        expect(requirement).toHaveValue("Keep this exact local text");
    });

    it("renders the loaded dossier form without detectable accessibility violations", async () => {
        const profile = careerProfile();
        const fact = profile.facts[0];
        const { container } = render(<ApplicationDossier
            application={application({ resume_version_id: "version-1", dossiers: [] })}
            resumeVersions={[{ id: "version-1", selected_fact_ids: [fact.id] }]}
            onChanged={vi.fn()}
        />);
        await screen.findByRole("checkbox", { name: /Python.*requisito 1/i });

        await assertAccessible(container);
    });
});
