import { fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { resumeDraft } from "../../../test/fixtures";
import { ResumeCanvas } from "./ResumeCanvas";

describe("ResumeCanvas", () => {
    it("supports inline edits, undo and keyboard-accessible ordering", async () => {
        const user = userEvent.setup();
        const onChange = vi.fn();
        render(<ResumeCanvas document={resumeDraft().canvas_document} templateKind="ats" onChange={onChange} />);
        const title = screen.getByLabelText("Titolo blocco 1", { selector: "input[value='Principal Engineer']" });
        fireEvent.change(title, { target: { value: "Staff Engineer" } });
        expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ schema_version: 1 }));

        await user.click(screen.getByRole("button", { name: "Annulla modifica" }));
        expect(screen.getByDisplayValue("Principal Engineer")).toBeInTheDocument();
        const move = screen.getByRole("button", { name: "Sposta sezione Esperienza su" });
        move.focus();
        await user.keyboard("{Enter}");
        const paper = screen.getByLabelText("Canvas modificabile del CV");
        expect(paper.firstElementChild.querySelector('[aria-label="Titolo sezione experience"]')).not.toBeNull();
    });

    it("exposes visibility, page flow and ATS-safe style controls", async () => {
        const user = userEvent.setup();
        render(<ResumeCanvas document={resumeDraft().canvas_document} templateKind="ats" onChange={vi.fn()} />);
        expect(screen.getByText(/ATS · 1 colonna/)).toBeInTheDocument();
        expect(screen.queryByText("Colonne")).not.toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Nascondi sezione Esperienza" }));
        await user.click(screen.getByRole("button", { name: "Interruzione pagina prima di Esperienza" }));
        fireEvent.change(screen.getByLabelText("Dimensione testo"), { target: { value: "11" } });
        expect(screen.getByLabelText("Canvas modificabile del CV")).toHaveStyle({ "--canvas-size": "11pt" });
    });

    it("retains mobile, reduced-motion and keyboard fallbacks", async () => {
        const user = userEvent.setup();
        const careerCss = readFileSync("src/career-os.css", "utf8");
        render(<ResumeCanvas document={resumeDraft().canvas_document} templateKind="ats" onChange={vi.fn()} />);
        expect(careerCss).toContain("@media (max-width: 720px)");
        expect(careerCss).toContain("@media (prefers-reduced-motion: reduce)");
        expect(careerCss).toMatch(/\.canvas-section__controls[\s\S]*opacity:\s*1/);
        const moveButton = screen.getByRole("button", { name: "Sposta sezione Esperienza su" });
        moveButton.focus();
        expect(moveButton).toHaveFocus();
        await user.keyboard("{Enter}");
        expect(screen.getByLabelText("Canvas modificabile del CV").firstElementChild.querySelector('[aria-label="Titolo sezione experience"]')).not.toBeNull();
    });

    it("creates, warns about and promotes a manual claim", async () => {
        const user = userEvent.setup();
        const onPromoteClaim = vi.fn();
        render(<ResumeCanvas document={resumeDraft().canvas_document} templateKind="ats" onChange={vi.fn()} onPromoteClaim={onPromoteClaim} />);

        await user.click(screen.getByRole("button", { name: "Nuovo claim" }));
        expect(screen.getByText("Claim senza fonte")).toBeInTheDocument();
        const promote = screen.getByRole("button", { name: "Salva nel Career Vault" });
        expect(promote).toBeDisabled();
        const title = screen.getByLabelText("Titolo blocco 1", { selector: "input[value='']" });
        await user.type(title, "Ridotto il lavoro manuale del 30%");
        await user.click(promote);

        expect(onPromoteClaim).toHaveBeenCalledWith(expect.stringMatching(/^manual-/));
        await user.click(screen.getByRole("button", { name: /Rimuovi claim Ridotto il lavoro/ }));
        expect(screen.queryByText("Claim senza fonte")).not.toBeInTheDocument();
    });

    it("shows the normalized photo and applies the persisted photo column count", () => {
        const document = resumeDraft().canvas_document;
        document.style.columns = 2;
        const careerCss = readFileSync("src/career-os.css", "utf8");
        render(<ResumeCanvas document={document} templateKind="photo" photoUrl="blob:normalized-photo" onChange={vi.fn()} />);

        expect(screen.getByRole("img", { name: "Foto profilo normalizzata" })).toHaveAttribute("src", "blob:normalized-photo");
        expect(screen.getByLabelText("Canvas modificabile del CV")).toHaveStyle({ "--canvas-columns": "2" });
        expect(careerCss).toMatch(/resume-canvas-paper--photo[\s\S]*column-count:\s*var\(--canvas-columns\)/);
    });
});
