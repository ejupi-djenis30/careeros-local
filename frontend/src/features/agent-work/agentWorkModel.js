export const WORK_KINDS = Object.freeze(["discover", "analyze", "materials"]);

export const WORK_STATES = Object.freeze([
    "queued",
    "returned",
    "accepted",
    "rejected",
    "canceled",
    "expired",
]);

export const GATE_DECISIONS = Object.freeze(["eligible", "hold", "reject"]);

export function workErrorMessage(error, t, fallbackKey = "agentWork.error.general") {
    const code = error?.details?.detail?.code || error?.details?.code;
    const errorMap = {
        grant_required: "agentWork.error.grantRequired",
        grant_expired: "agentWork.error.grantExpired",
        grant_revoked: "agentWork.error.grantRevoked",
        scope_denied: "agentWork.error.scopeDenied",
        work_not_found: "agentWork.error.workNotFound",
        work_expired: "agentWork.error.workExpired",
        work_canceled: "agentWork.error.workCanceled",
        stale_input: "agentWork.error.staleInput",
        invalid_result: "agentWork.error.invalidResult",
        evidence_invalid: "agentWork.error.evidenceInvalid",
        result_conflict: "agentWork.error.resultConflict",
        revision_conflict: "agentWork.error.revisionConflict",
        vault_unavailable: "agentWork.error.vaultUnavailable",
        desktop_unavailable: "agentWork.error.desktopUnavailable",
        authentication_failed: "agentWork.error.authFailed",
    };

    if (code && errorMap[code]) {
        return t(errorMap[code]);
    }
    return error?.message || t(fallbackKey);
}

export function formatCopyablePrompt(request) {
    if (!request?.id) return "";
    return `Please process CareerOS agent work request ${request.id} using get_work_context and submit_work_result.`;
}

export function canCancel(work) {
    return work?.state === "queued" || work?.state === "returned";
}

export function proposalPayload(proposal) {
    return proposal?.payload && typeof proposal.payload === "object" ? proposal.payload : null;
}

export function proposalSupportsReview(work, proposal) {
    const payload = proposalPayload(proposal);
    if (!payload || payload.contract_version !== 1 || payload.kind !== work?.work_kind) return false;
    if (payload.kind === "discover") {
        return Array.isArray(payload.listings)
            && payload.listings.length > 0
            && payload.listings.every((listing) => (
                typeof listing.external_url === "string"
                && typeof listing.source_text === "string"
                && Array.isArray(listing.gates)
                && listing.scores
            ));
    }
    if (payload.kind === "analyze") {
        return Array.isArray(payload.gates)
            && payload.scores
            && Array.isArray(payload.claims)
            && payload.claims.length > 0
            && typeof payload.recommendation === "string";
    }
    if (payload.kind === "materials") {
        return typeof payload.preset_id === "string"
            && Number.isInteger(payload.preset_version)
            && typeof payload.locale === "string"
            && Array.isArray(payload.cv_selected_fact_ids)
            && payload.cv_selected_fact_ids.length > 0
            && Array.isArray(payload.cv_cited_overrides)
            && Array.isArray(payload.cover_letter)
            && payload.email
            && Array.isArray(payload.questions_answers)
            && Array.isArray(payload.requirements_to_evidence)
            && payload.requirements_to_evidence.length > 0;
    }
    return false;
}

export function canReview(work) {
    return work?.state === "returned";
}

export function canAccept(work) {
    return work?.state === "returned";
}

export function canReject(work) {
    return work?.state === "returned";
}

export function isTerminalState(work) {
    return ["accepted", "rejected", "canceled", "expired"].includes(work?.state);
}

export function filterWork(items = [], { state = "all", query = "" } = {}) {
    let filtered = Array.isArray(items) ? [...items] : [];
    if (state && state !== "all") {
        filtered = filtered.filter((item) => item.state === state);
    }
    if (query && query.trim()) {
        const q = query.trim().toLowerCase();
        filtered = filtered.filter((item) => (
            (item.instruction && item.instruction.toLowerCase().includes(q))
            || (item.id && item.id.toLowerCase().includes(q))
            || (item.work_kind && item.work_kind.toLowerCase().includes(q))
        ));
    }
    return filtered;
}
