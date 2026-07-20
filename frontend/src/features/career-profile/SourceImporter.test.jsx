import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CareerService } from "../../services/career";
import { renderWithItalian as render } from "../../test/renderWithI18n";
import { SourceImporter } from "./SourceImporter";

vi.mock("../../services/career", () => ({
    CareerService: { uploadSource: vi.fn() },
}));

const imported = {
    id: "source-1",
    original_name: "career.txt",
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
};

describe("SourceImporter", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        CareerService.uploadSource.mockResolvedValue(imported);
    });

    it("previews local text and requires explicit candidate acceptance", async () => {
        const user = userEvent.setup();
        const accept = vi.fn(() => 1);
        render(<SourceImporter onAcceptCandidates={accept} />);

        await user.upload(screen.getByLabelText("Documento sorgente"), new File(["career"], "career.txt", { type: "text/plain" }));
        await user.click(screen.getByRole("button", { name: "Importa localmente" }));

        expect(await screen.findByText("Candidati da revisionare")).toBeInTheDocument();
        await user.click(screen.getByText("Anteprima del testo estratto"));
        expect(screen.getAllByText(/Competenze: Python/)).toHaveLength(2);
        expect(accept).not.toHaveBeenCalled();

        await user.click(screen.getByRole("checkbox", { name: /Python/ }));
        await user.click(screen.getByRole("button", { name: "Accetta 1 candidati selezionati" }));

        expect(accept).toHaveBeenCalledWith(imported, [imported.candidates[0]]);
        expect(screen.getByRole("status")).toHaveTextContent("1 fatto aggiunto");
    });
});
