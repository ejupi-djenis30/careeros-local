import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CareerService } from "../../services/career";
import { renderWithItalian as render } from "../../test/renderWithI18n";
import { SourceImporter } from "./SourceImporter";

vi.mock("../../services/career", () => ({
    CareerService: { uploadSource: vi.fn() },
}));

const importedProfile = {
    id: "source-1",
    original_name: "career.txt",
    source_role: "profile",
    extracted_characters: 42,
    sha256: "a".repeat(64),
    text_preview: "Competenze: Python\nRiduzione del lead time del 30%.",
    candidates: [
        {
            candidate_id: "b".repeat(64),
            fact_type: "skill",
            payload: { name: "Python", level: "working" },
            source_locator: "paragraph:1:skill:1",
            confidence: 0.82,
            excerpt: "Competenze: Python",
        },
        {
            candidate_id: "c".repeat(64),
            fact_type: "achievement",
            payload: { title: "Riduzione del lead time del 30%", description: "Riduzione del lead time del 30%." },
            source_locator: "paragraph:2",
            confidence: 0.58,
            excerpt: "Riduzione del lead time del 30%.",
        },
    ],
    preference_candidates: [],
    review_notes: [],
    warnings: [],
};

const importedGoals = {
    id: "source-2",
    original_name: "Goal.md",
    source_role: "goals",
    extracted_characters: 120,
    sha256: "d".repeat(64),
    text_preview: "Target roles: Principal Engineer\nWorkload: 80-100%",
    candidates: [],
    preference_candidates: [
        {
            candidate_id: "e".repeat(64),
            field: "target_roles",
            value: ["Principal Engineer"],
            source_locator: "line:1:preference:target_roles",
            excerpt: "Target roles: Principal Engineer",
        },
        {
            candidate_id: "f".repeat(64),
            field: "workload_min",
            value: 80,
            source_locator: "line:2:preference:workload_min",
            excerpt: "Workload: 80-100%",
        },
    ],
    review_notes: [
        "Prose retained for manual review: 'Lead architectural governance' (goals do not generate career achievements).",
    ],
    warnings: [],
};

const importedNarrative = {
    id: "source-3",
    original_name: "Storytelling.md",
    source_role: "narrative",
    extracted_characters: 85,
    sha256: "1".repeat(64),
    text_preview: "Personal storytelling journey.",
    candidates: [],
    preference_candidates: [],
    review_notes: [
        "Conserva la prosa per revisione manuale. Non genera automaticamente fatti professionali.",
    ],
    warnings: [],
};

describe("SourceImporter", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        CareerService.uploadSource.mockResolvedValue(importedProfile);
    });

    it("previews local text and requires explicit candidate acceptance", async () => {
        const user = userEvent.setup();
        const accept = vi.fn(() => 1);
        const prepare = vi.fn();
        const review = vi.fn();
        render(<SourceImporter onAcceptCandidates={accept} onPrepareImport={prepare} onReviewAccepted={review} />);

        // Verify deterministic parser disclosure note is present
        expect(screen.getByRole("note")).toHaveTextContent("Analisi deterministica locale");

        await user.upload(screen.getByLabelText("Documento sorgente"), new File(["career"], "career.txt", { type: "text/plain" }));
        await user.click(screen.getByRole("button", { name: "Importa localmente" }));

        expect(await screen.findByText("Candidati da revisionare")).toBeInTheDocument();
        expect(prepare.mock.invocationCallOrder[0]).toBeLessThan(CareerService.uploadSource.mock.invocationCallOrder[0]);
        await user.click(screen.getByText("Anteprima del testo estratto"));
        expect(screen.getAllByText(/Competenze: Python/)).toHaveLength(2);
        expect(accept).not.toHaveBeenCalled();

        await user.click(screen.getByRole("checkbox", { name: /Python/ }));
        await user.click(screen.getByRole("button", { name: "Accetta 1 candidati selezionati" }));

        expect(accept).toHaveBeenCalledWith(importedProfile, [importedProfile.candidates[0]]);
        expect(screen.getByRole("status")).toHaveTextContent("1 fatto aggiunto");
        await user.click(screen.getByRole("button", { name: "Controlla i fatti importati" }));
        expect(review).toHaveBeenCalledTimes(1);
    });

    it("supports selecting goals role and accepting explicit preference candidates", async () => {
        const user = userEvent.setup();
        CareerService.uploadSource.mockResolvedValueOnce(importedGoals);
        const acceptPrefs = vi.fn(() => 1);
        const reviewPrefs = vi.fn();
        render(<SourceImporter onAcceptPreferences={acceptPrefs} onReviewAcceptedPreferences={reviewPrefs} />);

        // Select 'goals' role from dropdown
        const roleSelect = screen.getByLabelText("Ruolo del documento sorgente");
        await user.selectOptions(roleSelect, "goals");

        const file = new File(["goals content"], "Goal.md", { type: "text/markdown" });
        await user.upload(screen.getByLabelText("Documento sorgente"), file);
        await user.click(screen.getByRole("button", { name: "Importa localmente" }));

        expect(CareerService.uploadSource).toHaveBeenCalledWith(file, "goals");

        // Preference candidates section must be visible and unselected by default
        expect(await screen.findByText("Candidati preferenze")).toBeInTheDocument();
        const checkboxes = screen.getAllByRole("checkbox");
        expect(checkboxes).toHaveLength(2);
        expect(checkboxes[0]).not.toBeChecked();
        expect(checkboxes[1]).not.toBeChecked();

        // Review notes must be displayed
        expect(screen.getByText(/Note di revisione/)).toBeInTheDocument();

        // Select first preference and accept
        await user.click(checkboxes[0]);
        const acceptBtn = screen.getByRole("button", { name: "Accetta 1 preferenze selezionate" });
        await user.click(acceptBtn);

        expect(acceptPrefs).toHaveBeenCalledWith(importedGoals, [importedGoals.preference_candidates[0]]);
        expect(screen.getByRole("status")).toHaveTextContent("1 preferenza/e applicata/e alla bozza del profilo.");

        await user.click(screen.getByRole("button", { name: "Controlla le preferenze accettate" }));
        expect(reviewPrefs).toHaveBeenCalledTimes(1);
    });

    it("supports narrative role and displays review notes without fact candidates", async () => {
        const user = userEvent.setup();
        CareerService.uploadSource.mockResolvedValueOnce(importedNarrative);
        render(<SourceImporter />);

        const roleSelect = screen.getByLabelText("Ruolo del documento sorgente");
        await user.selectOptions(roleSelect, "narrative");

        const file = new File(["narrative text"], "Storytelling.md", { type: "text/markdown" });
        await user.upload(screen.getByLabelText("Documento sorgente"), file);
        await user.click(screen.getByRole("button", { name: "Importa localmente" }));

        expect(CareerService.uploadSource).toHaveBeenCalledWith(file, "narrative");
        expect(await screen.findByText(/Note di revisione/)).toBeInTheDocument();
        // Facts candidates are not present
        expect(screen.queryByText("Candidati da revisionare")).not.toBeInTheDocument();
    });

    it("keeps the selected file available when preparation fails, then retries explicitly", async () => {
        const user = userEvent.setup();
        const prepare = vi.fn()
            .mockRejectedValueOnce(new Error("Career Vault could not be saved"))
            .mockResolvedValueOnce();
        render(<SourceImporter firstRun onPrepareImport={prepare} />);

        const file = new File(["career"], "career.txt", { type: "text/plain" });
        await user.upload(screen.getByLabelText("Documento sorgente"), file);
        await user.click(screen.getByRole("button", { name: "Importa localmente" }));

        expect(await screen.findByRole("alert")).toHaveTextContent("Career Vault could not be saved");
        expect(CareerService.uploadSource).not.toHaveBeenCalled();
        expect(screen.getByText("career.txt")).toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: "Importa localmente" }));
        expect(await screen.findByText("Candidati da revisionare")).toBeInTheDocument();
        expect(prepare).toHaveBeenCalledTimes(2);
        expect(CareerService.uploadSource).toHaveBeenCalledWith(file, "profile");
    });

    it("keeps the selected file available when the local upload fails", async () => {
        const user = userEvent.setup();
        CareerService.uploadSource.mockRejectedValueOnce(new Error("Local document import failed"));
        render(<SourceImporter />);

        await user.upload(screen.getByLabelText("Documento sorgente"), new File(["career"], "career.txt", { type: "text/plain" }));
        await user.click(screen.getByRole("button", { name: "Importa localmente" }));

        expect(await screen.findByRole("alert")).toHaveTextContent("Local document import failed");
        expect(screen.getByText("career.txt")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Importa localmente" })).toBeEnabled();
    });

    it("locks file and role identity while an upload response is pending", async () => {
        const user = userEvent.setup();
        let finishUpload;
        CareerService.uploadSource.mockImplementationOnce(() => new Promise((resolve) => {
            finishUpload = resolve;
        }));
        render(<SourceImporter />);

        const role = screen.getByLabelText("Ruolo del documento sorgente");
        const input = screen.getByLabelText("Documento sorgente");
        await user.selectOptions(role, "goals");
        await user.upload(input, new File(["goals"], "GoalA.md", { type: "text/markdown" }));
        await user.click(screen.getByRole("button", { name: "Importa localmente" }));

        await waitFor(() => expect(CareerService.uploadSource).toHaveBeenCalled());
        expect(role).toBeDisabled();
        expect(input).toBeDisabled();
        finishUpload(importedGoals);
        expect(await screen.findByText("Candidati preferenze")).toBeInTheDocument();
        expect(role).toBeEnabled();
        expect(input).toBeEnabled();
    });

    it("retains selected preferences when the combined profile rejects them", async () => {
        const user = userEvent.setup();
        CareerService.uploadSource.mockResolvedValueOnce(importedGoals);
        render(<SourceImporter onAcceptPreferences={() => 0} />);

        await user.selectOptions(screen.getByLabelText("Ruolo del documento sorgente"), "goals");
        await user.upload(
            screen.getByLabelText("Documento sorgente"),
            new File(["goals"], "Goal.md", { type: "text/markdown" }),
        );
        await user.click(screen.getByRole("button", { name: "Importa localmente" }));
        const candidate = await screen.findByRole("checkbox", { name: /Ruoli desiderati: Principal Engineer/ });
        await user.click(candidate);
        await user.click(screen.getByRole("button", { name: "Accetta 1 preferenze selezionate" }));

        expect(candidate).toBeChecked();
    });
});
