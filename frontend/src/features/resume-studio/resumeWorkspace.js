import { ApiError } from "../../lib/client";
import { CareerService } from "../../services/career";
import { ResumeService } from "../../services/resumes";

const EDITABLE_FIELDS = [
    "title", "template_kind", "template_layout", "template_id", "template_version",
    "locale", "section_config", "selected_fact_ids", "content_overrides",
    "canvas_document", "photo_asset_id",
];

export function mergeResumeResponse(current, response, editedFields) {
    const edits = Object.fromEntries(EDITABLE_FIELDS
        .filter((field) => editedFields.has(field))
        .map((field) => [field, current[field]]));
    return { ...response, ...edits };
}

export async function loadResumeWorkspace({ requestedResumeId, freshDraft, signal }) {
    const options = { signal, suppressGlobalError: true };
    const profileRequest = CareerService.getProfile({ ...options, suppressGlobalError: true })
        .then((value) => ({ value }))
        .catch((error) => ({ error }));
    const [profileResult, resumes] = await Promise.all([profileRequest, ResumeService.list(options)]);
    if (signal.aborted) return null;
    if (profileResult.error) return { profileError: profileResult.error };
    const profile = profileResult.value;
    const hasTarget = requestedResumeId !== null;
    const validTarget = typeof requestedResumeId === "string"
        && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(requestedResumeId);
    const target = hasTarget && validTarget
        ? resumes.find((resume) => resume.id.toLowerCase() === requestedResumeId.toLowerCase())
        : null;
    const unavailable = { profile, resumes, draft: null, targetUnavailable: true };
    if (hasTarget && !target) return unavailable;
    try {
        const draft = resumes.length
            ? await ResumeService.get(target?.id || resumes[0].id, options)
            : freshDraft(profile.facts);
        return { profile, resumes, draft };
    } catch (error) {
        if (hasTarget && error instanceof ApiError && error.status === 404) return unavailable;
        throw error;
    }
}
