let fallbackRowId = 0;
function rowId() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    fallbackRowId += 1;
    return `dossier-row-${fallbackRowId}`;
}

export const requirementRow = () => ({ id: rowId(), requirement: "", evidenceFactIds: [] });
export const answerRow = () => ({ id: rowId(), question: "", answer: "" });
export const checklistRow = () => ({ id: rowId(), label: "", completed: false });
export const blankForm = () => ({
    requirements: [requirementRow()],
    coverLetter: "",
    answers: [answerRow()],
    checklist: [checklistRow()],
    letterOptions: null,
    emailDraft: null,
    evidenceClaims: [],
    generationProvenance: null,
});
export const LIMITS = Object.freeze({
    requirements: 25,
    evidencePerRequirement: 10,
    evidenceLinks: 100,
    uniqueFacts: 50,
    answers: 25,
    checklist: 50,
    coverLetter: 30000,
});

export function draftContent({ requirements, coverLetter, answers, checklist, letterOptions, emailDraft, evidenceClaims, generationProvenance }) {
    return {
        cover_letter: coverLetter || null,
        answers: answers.map((row) => ({
            client_id: row.id,
            question: row.question,
            answer: row.answer,
        })),
        checklist: checklist.map((row) => ({
            client_id: row.id,
            label: row.label,
            completed: row.completed,
        })),
        requirement_matrix: requirements.map((row) => ({
            client_id: row.id,
            requirement: row.requirement,
            evidence_fact_ids: row.evidenceFactIds,
        })),
        ...(letterOptions ? { letter_options: letterOptions } : {}),
        ...(emailDraft ? { email_draft: emailDraft } : {}),
        ...(evidenceClaims?.length ? { evidence_claims: evidenceClaims } : {}),
        ...(generationProvenance ? { generation_provenance: generationProvenance } : {}),
    };
}

export function formFromDraft(draft) {
    const content = draft?.content || {};
    return {
        requirements: (content.requirement_matrix || []).map((row) => ({
            id: row.client_id,
            requirement: row.requirement,
            evidenceFactIds: row.evidence_fact_ids,
        })),
        coverLetter: content.cover_letter || "",
        answers: (content.answers || []).map((row) => ({
            id: row.client_id,
            question: row.question,
            answer: row.answer,
        })),
        checklist: (content.checklist || []).map((row) => ({
            id: row.client_id,
            label: row.label,
            completed: row.completed,
        })),
        letterOptions: content.letter_options || null,
        emailDraft: content.email_draft || null,
        evidenceClaims: content.evidence_claims || [],
        generationProvenance: content.generation_provenance || null,
    };
}

export function publishContent(content) {
    const { answers, checklist, requirement_matrix, ...rest } = content;
    return {
        ...rest,
        cover_letter: (content.cover_letter || "").trim() || null,
        answers: answers.filter((row) => row.question.trim() && row.answer.trim())
            .map((row) => ({ question: row.question.trim(), answer: row.answer.trim() })),
        checklist: checklist.filter((row) => row.label.trim())
            .map((row) => ({ label: row.label.trim(), completed: row.completed })),
        requirement_matrix: requirement_matrix.map((row) => ({
            requirement: row.requirement.trim(), evidence_fact_ids: row.evidence_fact_ids,
        })),
    };
}

export function draftBinding(draft, application) {
    return draft?.resume_draft_id ? {
        resume_draft_id: draft.resume_draft_id,
        expected_resume_draft_revision: draft.resume_draft_revision,
    } : { resume_version_id: draft?.resume_version_id || application.resume_version_id || null };
}

export const DOWNLOAD_FILES = Object.freeze([
    "resume.pdf", "resume.docx", "cover_letter.pdf", "cover_letter.docx", "email_draft.eml", "email_checklist.txt",
]);

export function publishedFiles(application, dossierId) {
    const event = application.events?.find((entry) => entry.id === dossierId && entry.event_type === "dossier_published");
    const entries = event?.payload?.dossier?.manifest?.entries || [];
    return DOWNLOAD_FILES.filter((filename) => entries.some((entry) => entry.path === filename));
}
