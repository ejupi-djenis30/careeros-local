import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { careerProfile, EXPERIENCE_ID, FACT_ID, GOAL_ID, resumeDraft, RESUME_ID } from "../../test/fixtures";
import { assertAccessible } from "../../test/accessibility";
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
const compareVersions = vi.fn();
const restoreVersion = vi.fn();
const getProfile = vi.fn();
const showToast = vi.fn();

vi.mock("../../services/career", () => ({ CareerService: { getProfile: (...args) => getProfile(...args), uploadPhoto: vi.fn() } }));
vi.mock("../../services/resumes", () => ({ ResumeService: { list: (...args) => list(...args), get: (...args) => get(...args), create: (...args) => create(...args), generate: (...args) => generate(...args), duplicate: (...args) => duplicate(...args), promoteClaim: (...args) => promoteClaim(...args), sync: (...args) => sync(...args), update: (...args) => update(...args), publish: (...args) => publish(...args), compareVersions: (...args) => compareVersions(...args), restoreVersion: (...args) => restoreVersion(...args), remove: vi.fn(), downloadArtifact: vi.fn() } }));
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
        compareVersions.mockResolvedValue({ left_name: "Alpha", right_name: "Beta", profile_changes: [], resume_changes: ["title"], added_fact_ids: [], removed_fact_ids: [], changed_fact_ids: [] });
        restoreVersion.mockResolvedValue(resumeDraft({ revision: 2 }));
        get.mockResolvedValue(resumeDraft({ versions: [{ id: "v1", name: "Candidatura Alpha", version_number: 1, semantic_version: "1.0.0", profile_revision: 3, selected_fact_ids: [FACT_ID], template_kind: "ats", renderer_version: "1", published_at: "2026-01-03T10:00:00Z", quality_report: { passed: true, page_count: 1 }, artifacts: [] }] }));
    });

    it("persists a fact selection before publishing verified artifacts", async () => {
        const user = userEvent.setup();
        render(<ResumeStudioPage />);
        const versionName = await screen.findByLabelText("Nome prossima versione");
        await user.clear(versionName);
        await user.type(versionName, "Candidatura Alpha");
        const publishButton = await screen.findByRole("button", { name: "Pubblica PDF + DOCX" });
        await user.click(publishButton);

        await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
        expect(create.mock.calls[0][0]).toMatchObject({ template_kind: "ats", selected_fact_ids: [FACT_ID, EXPERIENCE_ID] });
        await waitFor(() => expect(publish).toHaveBeenCalledWith(RESUME_ID, "Candidatura Alpha"));
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

    it("autosaves an edited existing draft after the debounce", async () => {
        const user = userEvent.setup();
        list.mockResolvedValue([{ id: RESUME_ID, title: "CV ATS", template_kind: "ats", selected_fact_count: 2, latest_version: null }]);
        get.mockResolvedValue(resumeDraft());
        update.mockImplementation((_id, data) => Promise.resolve(resumeDraft({ revision: 2, title: data.title })));
        render(<ResumeStudioPage />);

        const title = await screen.findByLabelText("Titolo interno");
        await user.clear(title);
        await user.type(title, "CV autosalvato");

        await waitFor(() => expect(update).toHaveBeenCalledWith(
            RESUME_ID,
            expect.objectContaining({ title: "CV autosalvato", expected_revision: 1 }),
        ), { timeout: 3_000 });
        expect(await screen.findByText("Salvato automaticamente")).toBeInTheDocument();
    });

    it("compares and restores named immutable versions", async () => {
        const user = userEvent.setup();
        const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
        const versions = [
            { id: "v1", name: "Alpha", semantic_version: "1.0.0", profile_revision: 3, published_at: "2026-01-03T10:00:00Z", quality_report: { page_count: 1 }, artifacts: [] },
            { id: "v2", name: "Beta", semantic_version: "1.0.1", profile_revision: 3, published_at: "2026-01-04T10:00:00Z", quality_report: { page_count: 1 }, artifacts: [] },
        ];
        list.mockResolvedValue([{ id: RESUME_ID, title: "CV ATS", template_kind: "ats", selected_fact_count: 2, latest_version: "1.0.1" }]);
        get.mockResolvedValue(resumeDraft({ versions }));
        render(<ResumeStudioPage />);

        await user.click(await screen.findByLabelText("Seleziona versione Alpha"));
        await user.click(screen.getByLabelText("Seleziona versione Beta"));
        await user.click(screen.getByRole("button", { name: "Confronta 2 versioni" }));
        expect(await screen.findByText("Alpha → Beta")).toBeInTheDocument();
        expect(compareVersions).toHaveBeenCalledWith("v1", "v2");

        await user.click(screen.getAllByRole("button", { name: "Ripristina nella bozza" })[1]);
        expect(restoreVersion).toHaveBeenCalledWith(RESUME_ID, "v1", 1);
        expect(showToast).toHaveBeenCalledWith(expect.stringContaining("nuova revisione"), "success");
        confirm.mockRestore();
    });

    it("passes the resume canvas and export accessibility and keyboard gate", async () => {
        const user = userEvent.setup();
        const { container } = render(<main><ResumeStudioPage /></main>);
        const publishButton = await screen.findByRole("button", { name: "Pubblica PDF + DOCX" });

        await assertAccessible(container);
        publishButton.focus();
        expect(publishButton).toHaveFocus();
        await user.keyboard("{Enter}");
        await waitFor(() => expect(publish).toHaveBeenCalledWith(RESUME_ID, "Versione CV"));
    });

    it("aborts initialization requests when the studio unmounts", async () => {
        getProfile.mockImplementationOnce((options) => new Promise((_resolve, reject) => {
            options.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
        }));
        const { unmount } = render(<ResumeStudioPage />);

        await waitFor(() => expect(getProfile).toHaveBeenCalledTimes(1));
        const [{ signal }] = getProfile.mock.calls[0];
        expect(signal.aborted).toBe(false);

        unmount();

        expect(signal.aborted).toBe(true);
    });
});
