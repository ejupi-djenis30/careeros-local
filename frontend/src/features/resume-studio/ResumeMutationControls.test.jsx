import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderWithItalian as render } from "../../test/renderWithI18n";
import { careerProfile, resumeDraft } from "../../test/fixtures";
import { ResumeSettings } from "./ResumeSettings";
import { CanvasInspector } from "./canvas/CanvasInspector";

describe("resume mutation controls", () => {
    it("disables photo upload while another draft operation is pending", () => {
        const studio = {
            profile: careerProfile(), draft: resumeDraft({ template_kind: "photo", photo_asset_id: "photo" }),
            busy: "autosave", dirty: true, generationGoalId: "", versionName: "Version", autosaveState: "saving",
        };
        const { container } = render(<ResumeSettings studio={studio} />);
        expect(container.querySelector('input[type="file"]')).toBeDisabled();
    });

    it("disables claim promotion during another operation while keeping its action label", () => {
        render(<CanvasInspector selected={{ id: "claim", kind: "fact", fact_ids: [], content: { title: "Claim" } }}
            sectionId="section" dispatch={vi.fn()} onPromote={vi.fn()} promoting={false} mutationBusy />);
        expect(screen.getByRole("button", { name: "Salva nel Career Vault" })).toBeDisabled();
    });
});
