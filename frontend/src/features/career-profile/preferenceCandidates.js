const LIST_RULES = Object.freeze({
    target_roles: { max: 50 },
    preferred_locations: { max: 50 },
    preferred_languages: { max: 50 },
    preferred_work_modes: { max: 3, values: ["onsite", "hybrid", "remote"] },
    contract_types: {
        max: 10,
        values: ["permanent", "temporary", "contract", "freelance", "internship", "apprenticeship"],
    },
});

const SCALAR_RULES = Object.freeze({
    workload_min: { integer: true, min: 0, max: 100 },
    workload_max: { integer: true, min: 0, max: 100 },
    hard_max_distance_km: { min: 0 },
    notice_period_days: { integer: true, min: 0, max: 730 },
    remote_only: { boolean: true },
    available_from: { date: true },
});

export class PreferenceCandidateError extends Error {
    constructor(code, field) {
        super(`${code}:${field || "preferences"}`);
        this.name = "PreferenceCandidateError";
        this.code = code;
        this.field = field;
    }
}

function canonical(value) {
    return JSON.stringify(value);
}

function assertScalar(field, value) {
    const rule = SCALAR_RULES[field];
    if (!rule) throw new PreferenceCandidateError("unsupported", field);
    if (rule.boolean) {
        if (typeof value !== "boolean") throw new PreferenceCandidateError("invalid", field);
        return;
    }
    if (rule.date) {
        if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
            throw new PreferenceCandidateError("invalid", field);
        }
        const parsed = new Date(`${value}T00:00:00Z`);
        if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value) {
            throw new PreferenceCandidateError("invalid", field);
        }
        return;
    }
    if (typeof value !== "number" || !Number.isFinite(value)) {
        throw new PreferenceCandidateError("invalid", field);
    }
    if (rule.integer && !Number.isInteger(value)) throw new PreferenceCandidateError("invalid", field);
    if (value < rule.min || (rule.max != null && value > rule.max)) {
        throw new PreferenceCandidateError("invalid", field);
    }
}

function mergeList(field, existing, incoming) {
    const rule = LIST_RULES[field];
    if (!rule || !Array.isArray(incoming)) throw new PreferenceCandidateError("unsupported", field);
    const merged = Array.isArray(existing) ? [...existing] : [];
    for (const item of incoming) {
        if (typeof item !== "string" || !item.trim()) throw new PreferenceCandidateError("invalid", field);
        const normalized = item.trim();
        if (rule.values && !rule.values.includes(normalized)) {
            throw new PreferenceCandidateError("invalid", field);
        }
        if (!merged.includes(normalized)) merged.push(normalized);
    }
    if (merged.length > rule.max) throw new PreferenceCandidateError("limit", field);
    return merged;
}

export function mergePreferenceCandidates(currentPreferences, candidates) {
    const next = structuredClone(currentPreferences || {});
    const selectedScalars = new Map();

    for (const candidate of candidates || []) {
        if (Array.isArray(candidate.value)) {
            next[candidate.field] = mergeList(candidate.field, next[candidate.field], candidate.value);
            continue;
        }
        assertScalar(candidate.field, candidate.value);
        const values = selectedScalars.get(candidate.field) || new Set();
        values.add(canonical(candidate.value));
        selectedScalars.set(candidate.field, values);
        if (values.size > 1) throw new PreferenceCandidateError("scalarConflict", candidate.field);
        next[candidate.field] = candidate.value;
    }

    if (next.workload_min != null && next.workload_max != null && next.workload_min > next.workload_max) {
        throw new PreferenceCandidateError("workload", "workload_min");
    }
    if (next.remote_only && Array.isArray(next.preferred_work_modes)
        && next.preferred_work_modes.length > 0 && !next.preferred_work_modes.includes("remote")) {
        throw new PreferenceCandidateError("remote", "preferred_work_modes");
    }
    return next;
}
