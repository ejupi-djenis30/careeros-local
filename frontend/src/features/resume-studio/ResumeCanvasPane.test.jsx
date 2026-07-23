import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { careerProfile, resumeDraft } from "../../test/fixtures";
import { renderWithItalian as render } from "../../test/renderWithI18n";
import { ResumeCanvasPane } from "./ResumeCanvasPane";

describe("ResumeCanvasPane", () => {
    it("keeps the active canvas control mounted across an autosave revision", async () => {
        const user = userEvent.setup();
        const onChange = vi.fn();
        const onPromoteClaim = vi.fn();
        const profile = careerProfile();
        const initial = resumeDraft();
        const { rerender } = render(
            <ResumeCanvasPane profile={profile} draft={initial} dirty onChange={onChange} onPromoteClaim={onPromoteClaim} promoting={false} />,
        );

        await user.click(screen.getByRole("button", { name: "Nuovo claim" }));
        await user.type(screen.getByLabelText("Titolo blocco 1", { selector: "input[value='']" }), "Creato un workflow locale");
        const promote = screen.getByRole("button", { name: "Salva nel Career Vault" });
        const savedDocument = onChange.mock.calls.at(-1)[0];

        rerender(
            <ResumeCanvasPane profile={profile} draft={resumeDraft({ revision: 2, canvas_document: savedDocument })} dirty={false} onChange={onChange} onPromoteClaim={onPromoteClaim} promoting={false} />,
        );

        expect(screen.getByRole("button", { name: "Salva nel Career Vault" })).toBe(promote);
        await user.click(promote);
        expect(onPromoteClaim).toHaveBeenCalledWith(expect.stringMatching(/^manual-/));
    });
});
