import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithI18n as render } from "../../test/renderWithI18n";
import { ResumeService } from "../../services/resumes";
import { TemplateGallery } from "./TemplateGallery";
import { selectTemplatePreset } from "./resumeModel";
import { assertAccessible } from "../../test/accessibility";

vi.mock("../../services/resumes", () => ({ ResumeService: { listTemplates: vi.fn() } }));
const ats = { id: "software-en", version: 1, name: "Software", family: "software", locale: "en", layout: "ats", template_kind: "ats", photo_policy: "forbidden", page_budget: 2, description: "Synthetic ATS", preview_style: { columns: 1, accent_color: "#111827" }, section_headings: { experience: "EXPERIENCE" } };
const swiss = { ...ats, id: "swiss-software-de", name: "Alpine preset", locale: "de", layout: "swiss-photo", template_kind: "photo", photo_policy: "optional", preview_style: { columns: 2, accent_color: "#1E3A8A" }, section_headings: { experience: "BERUFSERFAHRUNG" } };
const draft = { template_id: ats.id, template_kind: "ats", photo_asset_id: "remembered-photo", selected_fact_ids: ["A", "B"], canvas_document: { sections: [{ id: "experience", kind: "experience", title: "EXPERIENCE", blocks: [{ id: "manual", fact_ids: ["A", "B"], content: { title: "Approved wording" } }] }], style: { columns: 1, accent_color: "#111827" } } };
beforeEach(() => { vi.clearAllMocks(); ResumeService.listTemplates.mockResolvedValue([ats, swiss]); });

describe("TemplateGallery", () => {
    it("announces failure without offering fabricated fallback templates and retries", async () => {
        ResumeService.listTemplates.mockRejectedValueOnce(new Error("unavailable"));
        const user = userEvent.setup();
        render(<TemplateGallery studio={{ draft, changeDraft: vi.fn() }} onClose={vi.fn()} />);
        expect(await screen.findByRole("alert")).toHaveTextContent("Templates could not be loaded");
        expect(screen.queryByRole("button", { name: /Use this template/ })).not.toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Retry" }));
        expect(await screen.findByRole("button", { name: /Alpine preset/ })).toBeEnabled();
    });

    it("isolates focus, filters and preserves evidence and photo when choosing a preset", async () => {
        const user = userEvent.setup();
        const close = vi.fn(), changeDraft = vi.fn();
        const { container, unmount } = render(<TemplateGallery studio={{ draft, changeDraft }} onClose={close} />);
        expect(container.inert).toBe(true);
        expect(screen.getByRole("button", { name: "Close template gallery" })).toHaveFocus();
        await screen.findByRole("button", { name: /Alpine preset/ });
        await assertAccessible(screen.getByRole("dialog"));
        await user.tab({ shift: true });
        expect(screen.getByRole("button", { name: /Alpine preset/ })).toHaveFocus();
        await user.tab();
        expect(screen.getByRole("button", { name: "Close template gallery" })).toHaveFocus();
        await user.selectOptions(screen.getByLabelText("Language"), "de");
        expect(screen.queryByRole("heading", { name: "Software" })).not.toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: /Alpine preset/ }));
        const change = changeDraft.mock.calls[0][0];
        expect(change.photo_asset_id).toBe("remembered-photo");
        expect(change.canvas_document.sections[0].blocks).toEqual(draft.canvas_document.sections[0].blocks);
        expect(change.canvas_document.sections[0].title).toBe("BERUFSERFAHRUNG");
        expect(draft.canvas_document.sections[0].title).toBe("EXPERIENCE");
        await user.keyboard("{Escape}");
        expect(close).toHaveBeenCalledOnce();
        unmount();
        expect(container.inert).not.toBe(true);
    });

    it("aborts catalog requests when closed", async () => {
        ResumeService.listTemplates.mockImplementation(() => new Promise(() => {}));
        const { unmount } = render(<TemplateGallery studio={{ draft }} onClose={vi.fn()} />);
        await waitFor(() => expect(ResumeService.listTemplates).toHaveBeenCalledOnce());
        const signal = ResumeService.listTemplates.mock.calls[0][0].signal;
        unmount();
        expect(signal.aborted).toBe(true);
    });

    it("keeps custom headings and photo through a complete roundtrip", () => {
        const custom = structuredClone(draft);
        custom.canvas_document.sections[0].title = "Selected work";
        custom.canvas_document.style.accent_color = "#334455";
        const switched = { ...custom, ...selectTemplatePreset(custom, swiss, ats) };
        const returned = selectTemplatePreset(switched, ats, swiss);
        expect(returned.photo_asset_id).toBe(custom.photo_asset_id);
        expect(returned.canvas_document).toEqual(custom.canvas_document);
    });
});
