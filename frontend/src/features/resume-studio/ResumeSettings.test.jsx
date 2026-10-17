import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderWithI18n as render } from "../../test/renderWithI18n";
import { careerProfile, resumeDraft } from "../../test/fixtures";
import { ResumeSettings } from "./ResumeSettings";

describe("ResumeSettings template selector", () => {
    it.each([
        { language: "en", templateId: "software-en", label: "Template: software-en" },
        { language: "it", templateId: "software-en", label: "Modello: software-en" },
        { language: "en", templateId: undefined, label: "Choose template" },
        { language: "it", templateId: undefined, label: "Scegli modello" },
    ])("shows $label in $language", ({ language, templateId, label }) => {
        render(<ResumeSettings studio={{
            profile: careerProfile(),
            draft: resumeDraft({ template_id: templateId }),
            busy: "",
            dirty: false,
            generationGoalId: "",
            autosaveState: "idle",
            versionName: "Synthetic version",
            changeDraft: vi.fn(),
        }} />, { language });

        expect(screen.getByRole("button", { name: label, exact: true })).toBeEnabled();
        expect(screen.queryByText(/template\.(?:templateLabel|switchTemplate)/)).not.toBeInTheDocument();
    });
});
