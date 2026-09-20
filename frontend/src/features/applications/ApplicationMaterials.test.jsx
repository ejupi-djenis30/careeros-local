import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApplicationDossier } from "./ApplicationDossier";
import { application, careerProfile } from "../../test/fixtures";
import { assertAccessible } from "../../test/accessibility";
import { renderWithI18n as render } from "../../test/renderWithI18n";

const api = vi.hoisted(() => ({ getDossierDraft: vi.fn(), saveDossierDraft: vi.fn(), publishDossier: vi.fn(),
    deleteDossierDraft: vi.fn(), downloadDossier: vi.fn(), downloadDossierArtifact: vi.fn(), saveBlob: vi.fn(), listTemplates: vi.fn() }));
vi.mock("../../services/applications", () => ({ ApplicationService: api }));
vi.mock("../../services/career", () => ({ CareerService: { getProfile: vi.fn(async () => careerProfile()) } }));
vi.mock("../../services/resumes", () => ({ ResumeService: { listTemplates: api.listTemplates } }));
vi.mock("../../lib/download", () => ({ saveBlob: api.saveBlob }));

const defer = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };
function materialsDraft(applicationId = application().id) {
    const factId = careerProfile().facts[0].id;
    return { application_id: applicationId, revision: 3, application_revision: 1,
        resume_draft_id: "draft-1", resume_draft_revision: 4, resume_version_id: null,
        content: {
            cover_letter: "I build dependable Python services.",
            answers: [{ client_id: "answer-stable", question: "Why this job?", answer: "I build dependable Python services." }],
            checklist: [], requirement_matrix: [{ client_id: "requirement-stable", requirement: "Build services", evidence_fact_ids: [factId] }],
            letter_options: { preset_id: "swiss-software-de", template_version: 1, locale: "de", date: "2026-09-13", formats: ["pdf", "docx"] },
            email_draft: { mode: "motivational", subject: "Application", body: "I build dependable Python services.", recipient: null, attachment_names: ["resume.pdf", "cover_letter.pdf"] },
            generation_provenance: { source: "external-agent", request_id: "77777777-7777-4777-8777-777777777777" },
            evidence_claims: [{ id: "letter-claim", text: "I build dependable Python services.", fact_ids: [factId] }],
        } };
}
function props(overrides = {}) {
    const ids = [careerProfile().facts[0].id];
    return {
        application: application({ resume_version_id: "version-1", dossiers: [] }),
        resumeDrafts: [{ id: "draft-1", title: "Reviewed CV", revision: 4, selected_fact_ids: ids }],
        resumeVersions: [{ id: "version-1", draft_id: "draft-1", draft_revision: 4, selected_fact_ids: ids, label: "Reviewed CV v1" }],
        onChanged: vi.fn(), ...overrides,
    };
}

describe("MCP material preparation", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        api.getDossierDraft.mockResolvedValue(materialsDraft());
        api.saveDossierDraft.mockImplementation(async (_id, payload) => ({ ...materialsDraft(), ...payload,
            revision: (payload.expected_revision || 0) + 1, application_revision: payload.expected_application_revision }));
        api.publishDossier.mockResolvedValue(application({ resume_version_id: "version-1", revision: 2 }));
        api.listTemplates.mockResolvedValue([{ id: "swiss-software-de", version: 1, locale: "de", name: "Swiss software" }]);
    });

    it("loads complete accepted materials, targets the right MCP request, and publishes exact saved data only with an explicit CV", async () => {
        const user = userEvent.setup();
        const options = props();
        const { container } = render(<ApplicationDossier {...options} />);
        await screen.findByDisplayValue("Application");
        expect(screen.getByRole("link", { name: "Request materials via MCP" })).toHaveAttribute("href", `/agent-work?kind=materials&application_id=${options.application.id}&resume_id=draft-1`);
        expect(screen.getByRole("button", { name: "Publish dossier version" })).toBeDisabled();
        expect(screen.getByLabelText("Email style")).toHaveValue("motivational");
        expect(screen.getByLabelText("Letter date")).toHaveValue("2026-09-13");
        await waitFor(() => expect(screen.getByLabelText("Letter template")).not.toBeDisabled());
        await assertAccessible(container);
        fireEvent.change(screen.getByLabelText("Email subject"), { target: { value: "Reviewed subject" } });
        await user.selectOptions(screen.getByLabelText("Approved CV version for the packet"), "version-1");
        await user.click(screen.getByRole("button", { name: "Publish dossier version" }));
        await waitFor(() => expect(api.publishDossier).toHaveBeenCalledTimes(1));
        const saved = api.saveDossierDraft.mock.calls.at(-1)[1];
        expect(saved).toMatchObject({ resume_draft_id: "draft-1", expected_resume_draft_revision: 4 });
        expect(saved).not.toHaveProperty("resume_version_id");
        expect(saved.content.answers[0].client_id).toBe("answer-stable");
        expect(saved.content.requirement_matrix[0].client_id).toBe("requirement-stable");
        const sent = api.publishDossier.mock.calls[0][1];
        expect(sent).toMatchObject({ resume_version_id: "version-1", expected_draft_revision: 4,
            letter_options: saved.content.letter_options, email_draft: saved.content.email_draft,
            evidence_claims: saved.content.evidence_claims, generation_provenance: saved.content.generation_provenance });
        expect(sent.email_draft.subject).toBe("Reviewed subject");
        expect(options.onChanged).toHaveBeenCalledTimes(1);
    });

    it("excludes legacy and stale CV versions from the approved draft selector", async () => {
        const options = props();
        options.resumeVersions.push(
            { ...options.resumeVersions[0], id: "legacy", draft_revision: null, label: "Legacy version" },
            { ...options.resumeVersions[0], id: "stale", draft_revision: 3, label: "Earlier draft" },
        );
        render(<ApplicationDossier {...options} />);
        await screen.findByDisplayValue("Application");
        const select = screen.getByLabelText("Approved CV version for the packet");
        expect(Array.from(select.options).map((option) => option.value)).toEqual(["", "version-1"]);
    });

    it("does not replace unsaved material text with a refreshed proposal without a choice", async () => {
        const pending = defer();
        api.getDossierDraft.mockResolvedValueOnce(materialsDraft()).mockReturnValueOnce(pending.promise);
        render(<ApplicationDossier {...props()} />);
        await screen.findByDisplayValue("Application");
        fireEvent.change(screen.getByLabelText("Email subject"), { target: { value: "Local edit" } });
        await userEvent.click(screen.getByRole("button", { name: "Load accepted or saved materials" }));
        const remote = materialsDraft(); remote.content.email_draft.subject = "Accepted replacement";
        await act(async () => pending.resolve(remote));
        expect(screen.getByLabelText("Email subject")).toHaveValue("Local edit");
        expect(api.saveDossierDraft).not.toHaveBeenCalled();
        await userEvent.click(screen.getByRole("button", { name: "Load saved draft and replace local edits" }));
        expect(screen.getByLabelText("Email subject")).toHaveValue("Accepted replacement");
    });

    it("ignores a late refresh when a different application has opened", async () => {
        const pending = defer();
        const second = materialsDraft("application-b"); second.content.email_draft.subject = "Application B";
        api.getDossierDraft.mockResolvedValueOnce(materialsDraft()).mockReturnValueOnce(pending.promise).mockResolvedValueOnce(second);
        const options = props();
        const view = render(<ApplicationDossier {...options} />);
        await screen.findByDisplayValue("Application");
        await userEvent.click(screen.getByRole("button", { name: "Load accepted or saved materials" }));
        view.rerender(<ApplicationDossier {...options} application={application({ id: "application-b" })} />);
        await screen.findByDisplayValue("Application B");
        await act(async () => pending.resolve(materialsDraft()));
        expect(screen.getByLabelText("Email subject")).toHaveValue("Application B");
    });

    it("ignores a publication response after the editor has unmounted", async () => {
        const pending = defer(); api.publishDossier.mockReturnValueOnce(pending.promise);
        const options = props();
        const view = render(<ApplicationDossier {...options} />);
        await screen.findByDisplayValue("Application");
        await userEvent.selectOptions(screen.getByLabelText("Approved CV version for the packet"), "version-1");
        await userEvent.click(screen.getByRole("button", { name: "Publish dossier version" }));
        await waitFor(() => expect(api.publishDossier).toHaveBeenCalled());
        view.unmount();
        await act(async () => pending.resolve(application({ revision: 2 })));
        expect(options.onChanged).not.toHaveBeenCalled();
    });

    it("offers only supported published manifest files and downloads their immutable bytes", async () => {
        const artifact = { blob: new Blob(["offline email"]), filename: "email.eml" };
        api.downloadDossierArtifact.mockResolvedValue(artifact);
        const app = application({ resume_version_id: "version-1", dossiers: [{ id: "packet-1", version_number: 1, requirement_count: 1, completed_checklist: 0, checklist_total: 0, manifest_sha256: "a".repeat(64) }],
            events: [{ id: "packet-1", event_type: "dossier_published", payload: { dossier: { manifest: { entries: [{ path: "email_draft.eml" }, { path: "../private.txt" }] } } } }] });
        render(<ApplicationDossier {...props({ application: app })} />);
        await screen.findByDisplayValue("Application");
        await userEvent.click(screen.getByRole("button", { name: /Download email_draft.eml/ }));
        expect(api.downloadDossierArtifact).toHaveBeenCalledWith(app.id, "packet-1", "email_draft.eml");
        expect(api.saveBlob).toHaveBeenCalledWith(artifact);
        expect(screen.queryByRole("button", { name: /private.txt/ })).not.toBeInTheDocument();
    });
});
