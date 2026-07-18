export const FACT_TYPES = [
    ["experience", "Esperienza"],
    ["education", "Formazione"],
    ["project", "Progetto"],
    ["skill", "Competenza"],
    ["language", "Lingua"],
    ["certification", "Certificazione"],
    ["achievement", "Risultato"],
    ["volunteering", "Volontariato"],
    ["publication", "Pubblicazione"],
    ["link", "Link"],
    ["award", "Premio"],
    ["membership", "Associazione"],
    ["reference", "Referenza"],
    ["portfolio", "Portfolio"],
];

export const FACT_LABELS = Object.fromEntries(FACT_TYPES);

export const FACT_DEFAULTS = {
    experience: { role: "", organization: "", employment_type: "permanent", industry: "", location: "", work_mode: "hybrid", description: "", responsibilities: [], achievements: [], metrics: [], technologies: [], skills: [], team_size: null, current: false },
    education: { institution: "", qualification: "", field: "", grade: "", description: "", thesis: "", activities: [], coursework: [] },
    project: { name: "", role: "", organization: "", client: "", description: "", achievements: [], technologies: [], skills: [], url: "" },
    skill: { name: "", category: "", level: "working", years: null, last_used_date: "", evidence_fact_ids: [] },
    language: { language: "", level: "B2" },
    certification: { name: "", issuer: "", credential_id: "", url: "" },
    achievement: { title: "", description: "", details: [], metric_value: null, metric_unit: "", context: "", achieved_on: "" },
    volunteering: { title: "", organization: "", description: "", achievements: [] },
    publication: { title: "", publisher: "", published_on: "", description: "", url: "" },
    link: { label: "", url: "" },
    award: { title: "", issuer: "", awarded_on: "", description: "", url: "" },
    membership: { organization: "", role: "Membro", description: "", start_date: "", end_date: "", current: false, url: "" },
    reference: { name: "", relationship: "", organization: "", email: "", phone: "", notes: "", permission_to_contact: false },
    portfolio: { name: "", url: "", description: "", skills: [] },
};

export function emptyProfile(displayName = "Profilo locale") {
    return {
        expected_revision: 0,
        display_name: displayName,
        headline: "",
        summary: "",
        email: "",
        phone: "",
        location: {},
        birth_date: "",
        nationality: "",
        work_authorization: [],
        website: "",
        linkedin: "",
        github: "",
        preferences: {},
        facts: [],
        goals: [],
        analysis: null,
    };
}

function withoutEmpty(value) {
    if (Array.isArray(value)) {
        return value.map(withoutEmpty).filter((item) => item !== undefined && item !== "");
    }
    if (value && typeof value === "object") {
        return Object.fromEntries(
            Object.entries(value)
                .filter(([key]) => key !== "clientKey")
                .map(([key, item]) => [key, withoutEmpty(item)])
                .filter(([, item]) => item !== undefined && item !== ""),
        );
    }
    if (value === "" || value === null) return undefined;
    return value;
}

export function profileResponseToDraft(profile) {
    return {
        expected_revision: profile.revision,
        display_name: profile.display_name,
        headline: profile.headline || "",
        summary: profile.summary || "",
        email: profile.email || "",
        phone: profile.phone || "",
        location: profile.location || {},
        birth_date: profile.birth_date || "",
        nationality: profile.nationality || "",
        work_authorization: profile.work_authorization || [],
        website: profile.website || "",
        linkedin: profile.linkedin || "",
        github: profile.github || "",
        preferences: profile.preferences || {},
        facts: (profile.facts || []).map((fact) => ({ ...fact, clientKey: fact.id })),
        goals: (profile.goals || []).map((goal) => ({ ...goal, clientKey: goal.id })),
        analysis: profile.analysis || null,
    };
}

export function profileDraftToWrite(draft) {
    const value = withoutEmpty(draft);
    const writableItems = (items) => items.map((item) => Object.fromEntries(
        Object.entries(item).filter(([key]) => !["created_at", "updated_at"].includes(key)),
    ));
    return {
        expected_revision: draft.expected_revision,
        display_name: draft.display_name.trim(),
        headline: draft.headline.trim(),
        summary: draft.summary.trim(),
        email: value.email || null,
        phone: value.phone || null,
        location: value.location || {},
        birth_date: value.birth_date || null,
        nationality: value.nationality || null,
        work_authorization: value.work_authorization || [],
        website: value.website || null,
        linkedin: value.linkedin || null,
        github: value.github || null,
        preferences: value.preferences || {},
        facts: writableItems(value.facts || []),
        goals: writableItems(value.goals || []),
    };
}

export function newFact(type) {
    return {
        clientKey: crypto.randomUUID(),
        fact_type: type,
        position: 0,
        payload: structuredClone(FACT_DEFAULTS[type]),
        source_document_id: null,
        source_locator: null,
        confidence: null,
        verification_status: "confirmed",
    };
}

export function factTitle(fact) {
    const payload = fact.payload || {};
    return payload.role || payload.name || payload.title || payload.qualification || payload.language || payload.label || payload.organization || FACT_LABELS[fact.fact_type];
}

export function newGoal() {
    return {
        clientKey: crypto.randomUUID(),
        name: "Nuovo obiettivo",
        is_primary: false,
        payload: {
            status: "active",
            priority: 3,
            target_roles: [],
            target_industries: [],
            target_locations: [],
            target_seniority: [],
            work_modes: [],
            contract_types: [],
            compensation: null,
            rationale: "",
            start_date: "",
            target_date: "",
            progress_percent: 0,
            success_criteria: [],
            must_haves: [],
            deal_breakers: [],
            skill_gaps: [],
            milestones: [],
            actions: [],
            progress_notes: [],
        },
    };
}

export function profileCompleteness(profile) {
    const facts = profile.facts || [];
    const has = (type) => facts.some((fact) => fact.fact_type === type);
    const primaryGoal = profile.goals?.find((goal) => goal.is_primary) || profile.goals?.[0];
    const sections = [
        [15, [profile.display_name, profile.headline, profile.summary, profile.email || profile.phone, profile.location?.name || profile.location?.city || profile.location?.country]],
        [20, [has("experience"), facts.some((fact) => fact.fact_type === "experience" && fact.verification_status === "confirmed"), facts.some((fact) => fact.fact_type === "experience" && (fact.payload?.achievements?.length || fact.payload?.description))]],
        [15, [has("skill"), facts.some((fact) => fact.fact_type === "skill" && fact.verification_status === "confirmed"), facts.some((fact) => fact.fact_type === "skill" && fact.payload?.evidence_fact_ids?.length)]],
        [10, [has("education")]],
        [10, [has("achievement")]],
        [10, [has("project")]],
        [5, [facts.some((fact) => ["certification", "language", "award", "membership", "volunteering", "publication", "portfolio"].includes(fact.fact_type))]],
        [5, [profile.preferences?.target_roles?.length, profile.preferences?.preferred_work_modes?.length || profile.preferences?.remote_only, profile.preferences?.salary || profile.preferences?.salary_min_chf]],
        [10, [primaryGoal, primaryGoal?.payload?.target_roles?.length, primaryGoal?.payload?.target_date, primaryGoal?.payload?.success_criteria?.length, primaryGoal?.payload?.milestones?.length, primaryGoal?.payload?.actions?.length]],
    ];
    return Math.round(sections.reduce((total, [weight, checks]) => total + weight * checks.filter(Boolean).length / checks.length, 0));
}
