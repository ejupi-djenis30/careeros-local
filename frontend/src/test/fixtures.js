export const FACT_ID = "11111111-1111-4111-8111-111111111111";
export const PROFILE_ID = "22222222-2222-4222-8222-222222222222";
export const RESUME_ID = "33333333-3333-4333-8333-333333333333";
export const EXPERIENCE_ID = "66666666-6666-4666-8666-666666666666";
export const GOAL_ID = "77777777-7777-4777-8777-777777777777";

export function careerProfile(overrides = {}) {
    return {
        id: PROFILE_ID,
        user_id: 1,
        revision: 3,
        display_name: "Ada Lovelace",
        headline: "Software engineer",
        summary: "Costruisco sistemi affidabili.",
        email: "ada@example.test",
        phone: null,
        location: { name: "Zurigo" },
        birth_date: null,
        nationality: null,
        work_authorization: ["CH"],
        website: null,
        linkedin: null,
        github: null,
        photo_asset_id: null,
        preferences: {},
        facts: [{
            id: FACT_ID,
            fact_type: "skill",
            position: 0,
            payload: { name: "Python", level: "expert", years: 8 },
            source_document_id: null,
            source_locator: null,
            confidence: 1,
            verification_status: "confirmed",
            created_at: "2026-01-01T10:00:00Z",
            updated_at: "2026-01-01T10:00:00Z",
        }, {
            id: EXPERIENCE_ID,
            fact_type: "experience",
            position: 1,
            payload: {
                role: "Principal Engineer",
                organization: "Local Systems",
                employment_type: "permanent",
                industry: "Software",
                work_mode: "hybrid",
                start_date: "2020-01-01",
                current: true,
                description: "Guida piattaforme affidabili e rispettose della privacy.",
                responsibilities: ["Direzione tecnica", "Mentoring"],
                achievements: ["Ridotto il lead time del 40%."],
                metrics: ["40% più veloce"],
                technologies: ["Python", "React"],
                skills: ["Architecture"],
                team_size: 12,
            },
            source_document_id: null,
            source_locator: null,
            confidence: 1,
            verification_status: "confirmed",
            created_at: "2026-01-01T10:00:00Z",
            updated_at: "2026-01-01T10:00:00Z",
        }],
        goals: [{
            id: GOAL_ID,
            name: "Leadership tecnica",
            is_primary: true,
            payload: {
                status: "active",
                priority: 1,
                target_roles: ["Staff Engineer"],
                target_industries: ["Software"],
                target_locations: ["Svizzera"],
                target_seniority: ["staff"],
                work_modes: ["hybrid"],
                contract_types: ["permanent"],
                compensation: { currency: "CHF", minimum: 150000, period: "year" },
                must_haves: ["Leadership tecnica"],
                deal_breakers: [],
                skill_gaps: [],
                milestones: [],
                progress_notes: [],
            },
            created_at: "2026-01-01T10:00:00Z",
            updated_at: "2026-01-01T10:00:00Z",
        }],
        created_at: "2026-01-01T10:00:00Z",
        updated_at: "2026-01-01T10:00:00Z",
        ...overrides,
    };
}

export function resumeDraft(overrides = {}) {
    return {
        id: RESUME_ID,
        profile_id: PROFILE_ID,
        revision: 1,
        profile_revision: 3,
        title: "CV ATS",
        template_kind: "ats",
        section_config: {
            order: ["experience", "education", "project", "skill", "language", "certification", "achievement", "volunteering", "publication", "link"],
            include_summary: true,
            include_email: true,
            include_phone: true,
            include_location: true,
            include_links: true,
        },
        selected_fact_ids: [FACT_ID, EXPERIENCE_ID],
        content_overrides: {},
        canvas_document: {
            schema_version: 1,
            sections: [
                { id: "identity", kind: "identity", title: "Identità", visible: true, page_break_before: false, blocks: [{ id: "identity-main", kind: "identity", fact_ids: [], visible: true, content: { title: "Ada Lovelace", subtitle: "Software engineer", description: "", bullets: [] }, manual_fields: [] }] },
                { id: "experience", kind: "experience", title: "Esperienza", visible: true, page_break_before: false, blocks: [{ id: `fact-${EXPERIENCE_ID}`, kind: "fact", fact_ids: [EXPERIENCE_ID], visible: true, content: { title: "Principal Engineer", subtitle: "Local Systems", description: "Guida piattaforme affidabili e rispettose della privacy.", bullets: ["Ridotto il lead time del 40%."] }, manual_fields: [] }] },
            ],
            style: { font_family: "Helvetica", base_font_size: 10, line_height: 1.3, section_spacing: 10, margin_mm: 18, accent_color: "#243B53", columns: 1 },
        },
        generation_context: { mode: "deterministic", source_profile_revision: 3 },
        photo_asset_id: null,
        versions: [],
        created_at: "2026-01-01T10:00:00Z",
        updated_at: "2026-01-01T10:00:00Z",
        ...overrides,
    };
}

export function application(overrides = {}) {
    return {
        id: "44444444-4444-4444-8444-444444444444",
        user_id: 1,
        job_id: 42,
        resume_version_id: null,
        revision: 1,
        current_stage: "saved",
        job_snapshot: { title: "Backend Engineer", company: "Local Co", location: "Zurigo", external_url: "https://example.test/job" },
        events: [{ id: "55555555-5555-4555-8555-555555555555", event_type: "stage", stage: "saved", occurred_at: "2026-01-02T10:00:00Z", note: null, payload: {}, created_at: "2026-01-02T10:00:00Z" }],
        created_at: "2026-01-02T10:00:00Z",
        updated_at: "2026-01-02T10:00:00Z",
        ...overrides,
    };
}
