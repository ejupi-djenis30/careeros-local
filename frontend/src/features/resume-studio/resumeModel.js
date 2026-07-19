export const SECTION_ORDER = ["experience", "education", "project", "skill", "language", "certification", "achievement", "award", "membership", "portfolio", "volunteering", "publication", "link"];

export const SECTION_LABELS = {
    experience: "Experience",
    education: "Education",
    project: "Projects",
    skill: "Skills",
    language: "Languages",
    certification: "Certifications",
    achievement: "Achievements",
    volunteering: "Volunteering",
    publication: "Publications",
    link: "Link",
    award: "Awards",
    membership: "Memberships",
    portfolio: "Portfolio",
};

export function newResumeDraft(facts = []) {
    return {
        id: null,
        revision: null,
        title: "Main resume",
        template_kind: "ats",
        section_config: {
            order: SECTION_ORDER,
            include_summary: true,
            include_email: true,
            include_phone: true,
            include_location: true,
            include_links: true,
        },
        selected_fact_ids: facts.filter((fact) => fact.verification_status === "confirmed" && fact.fact_type !== "reference").map((fact) => fact.id),
        content_overrides: {},
        canvas_document: null,
        generation_context: null,
        photo_asset_id: null,
        versions: [],
    };
}

export function resumeWritePayload(draft) {
    const base = {
        title: draft.title.trim(),
        template_kind: draft.template_kind,
        section_config: draft.section_config,
        selected_fact_ids: draft.selected_fact_ids,
        content_overrides: draft.content_overrides || {},
        canvas_document: draft.canvas_document || null,
        photo_asset_id: draft.template_kind === "photo" ? draft.photo_asset_id : null,
    };
    if (draft.id) base.expected_revision = draft.revision;
    return base;
}

export function factHeading(fact) {
    const payload = fact.payload || {};
    return payload.role || payload.name || payload.title || payload.qualification || payload.language || payload.label || "Item";
}

export function factSubtitle(fact) {
    const payload = fact.payload || {};
    return payload.organization || payload.institution || payload.issuer || payload.role || payload.level || "";
}
