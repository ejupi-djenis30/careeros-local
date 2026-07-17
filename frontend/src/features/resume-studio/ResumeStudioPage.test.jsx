import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { careerProfile, EXPERIENCE_ID, FACT_ID, GOAL_ID, resumeDraft, RESUME_ID } from "../../test/fixtures";
import { ResumeStudioPage } from "./ResumeStudioPage";

const create = vi.fn();
const publish = vi.fn();
const get = vi.fn();
const list = vi.fn();
const generate = vi.fn();
const duplicate = vi.fn();
const sync = vi.fn();
const update = vi.fn();
const promoteClaim = vi.fn();
const getProfile = vi.fn();
const showToast = vi.fn();

vi.mock("../../services/career", () => ({ CareerService: { getProfile: (...args) => getProfile(...args), uploadPhoto: vi.fn() } }));
vi.mock("../../services/resumes", () => ({ ResumeService: { list: (...args) => list(...args), get: (...args) => get(...args), create: (...args) => create(...args), generate: (...args) => generate(...args), duplicate: (...args) => duplicate(...args), promoteClaim: (...args) => promoteClaim(...args), sync: (...args) => sync(...args), update: (...args) => update(...args), publish: (...args) => publish(...args), remove: vi.fn(), downloadArtifact: vi.fn() } }));
vi.mock("../../context/ToastContext", () => ({ useToast: () => ({ showToast }) }));

describe("ResumeStudioPage", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        getProfile.mockResolvedValue(careerProfile());
        list.mockResolvedValue([]);
        create.mockResolvedValue(resumeDraft());
        generate.mockResolvedValue(resumeDraft());
        update.mockImplementation((_id, data) => Promise.resolve(resumeDraft({ revision: 2, canvas_document: data.canvas_document })));
        promoteClaim.mockResolvedValue(resumeDraft({ revision: 3, profile_revision: 4 }));
        publish.mockResolvedValue({ id: "version" });
        get.mockResolvedValue(resumeDraft({ versions: [{ id: "v1", version_number: 1, semantic_version: "1.0.0", profile_revision: 3, selected_fact_ids: [FACT_ID], template_kind: "ats", renderer_version: "1", published_at: "2026-01-03T10:00:00Z", quality_report: { passed: true, page_count: 1 }, artifacts: [] }] }));
    });

    it("persists a fact selection before publishing verified artifacts", async () => {
        const user = userEvent.setup();
        render(<ResumeStudioPage />);
        const publishButton = await screen.findByRole("button", { name: "Pubblica PDF + DOCX" });
        await user.click(publishButton);

        await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
        expect(create.mock.calls[0][0]).toMatchObject({ template_kind: "ats", selected_fact_ids: [FACT_ID, EXPERIENCE_ID] });
        await waitFor(() => expect(publish).toHaveBeenCalledWith(RESUME_ID));
        expect(await screen.findByText("Quality gate superato")).toBeInTheDocument();
    });

    it("generates a complete canvas from the selected career goal", async () => {
        const user = userEvent.setup();
        render(<ResumeStudioPage />);
        await user.click(await screen.findByRole("button", { name: "Crea automaticamente" }));

        await waitFor(() => expect(generate).toHaveBeenCalledTimes(1));
        expect(generate).toHaveBeenCalledWith(expect.objectContaining({
            template_kind: "ats",
            career_goal_id: GOAL_ID,
        }));
        expect(await screen.findByLabelText("Canvas modificabile del CV")).toBeInTheDocument();
        expect(showToast).toHaveBeenCalledWith(expect.stringContaining("automaticamente"), "success");
    });

    it("duplicates a canvas and selectively synchronizes a newer profile", async () => {
        const user = userEvent.setup();
        getProfile.mockResolvedValue(careerProfile({ revision: 4 }));
        list.mockResolvedValue([{ id: RESUME_ID, title: "CV ATS", template_kind: "ats", selected_fact_count: 2, latest_version: null }]);
        get.mockResolvedValue(resumeDraft({ profile_revision: 3 }));
        sync
            .mockResolvedValueOnce({
                source_profile_revision: 3,
                current_profile_revision: 4,
                sections: [{ kind: "skill", added_fact_ids: [FACT_ID], removed_fact_ids: [], changed_fact_ids: [], conflicts: [] }],
                preserved_manual_fields: ["experience:title"],
                applied: false,
                draft: null,
            })
            .mockResolvedValueOnce({ applied: true, draft: resumeDraft({ revision: 2, profile_revision: 4 }) });
        duplicate.mockResolvedValue(resumeDraft({ id: "88888888-8888-4888-8888-888888888888", title: "CV ATS · copia" }));

        render(<ResumeStudioPage />);
        await user.click(await screen.findByRole("button", { name: /Career Vault contiene dati più recenti/ }));
        await user.click(await screen.findByLabelText("Sincronizza Competenze"));
        await user.click(screen.getByRole("button", { name: "Applica selezione" }));
        await waitFor(() => expect(sync).toHaveBeenLastCalledWith(RESUME_ID, {
            expected_revision: 1,
            mode: "apply",
            sections: ["skill"],
        }));

        await user.click(screen.getByRole("button", { name: "Duplica CV" }));
        await waitFor(() => expect(duplicate).toHaveBeenCalledWith(RESUME_ID, { title: "CV ATS · copia" }));
    });

    it("persists and promotes a canvas claim into the career profile", async () => {
        const user = userEvent.setup();
        list.mockResolvedValue([{ id: RESUME_ID, title: "CV ATS", template_kind: "ats", selected_fact_count: 2, latest_version: null }]);
        get.mockResolvedValue(resumeDraft());
        render(<ResumeStudioPage />);

        await user.click(await screen.findByRole("button", { name: "Nuovo claim" }));
        await user.type(screen.getByLabelText("Titolo blocco 1", { selector: "input[value='']" }), "Creato un workflow locale");
        await user.click(screen.getByRole("button", { name: "Salva nel Career Vault" }));

        await waitFor(() => expect(update).toHaveBeenCalledWith(
            RESUME_ID,
            expect.objectContaining({
                canvas_document: expect.objectContaining({
                    sections: expect.arrayContaining([expect.objectContaining({ kind: "achievement" })]),
                }),
            }),
        ));
        await waitFor(() => expect(promoteClaim).toHaveBeenCalledWith(
            RESUME_ID,
            expect.objectContaining({ expected_revision: 2, expected_profile_revision: 3 }),
        ));
        expect(showToast).toHaveBeenCalledWith(expect.stringContaining("fatto verificato"), "success");
    });
});
