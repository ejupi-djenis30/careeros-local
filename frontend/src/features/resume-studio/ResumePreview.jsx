import { SECTION_LABELS, SECTION_ORDER, factHeading, factSubtitle } from "./resumeModel";
import { useI18n } from "../../i18n/useI18n";

function ResumeFact({ fact, override, t }) {
    const payload = fact.payload || {};
    const description = override?.description ?? payload.description;
    const bullets = override?.bullets ?? payload.achievements ?? [];
    return (
        <article className="resume-preview__fact">
            <div><strong>{override?.title || factHeading(fact)}</strong>{factSubtitle(fact) && <span>{override?.subtitle || factSubtitle(fact)}</span>}</div>
            {description && <p>{description}</p>}
            {bullets.length > 0 && <ul>{bullets.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>}
            {fact.fact_type === "skill" && <p>{payload.level}{payload.years != null ? ` · ${t("resumePreview.years", { count: payload.years })}` : ""}</p>}
        </article>
    );
}

export function ResumePreview({ profile, draft }) {
    const { t } = useI18n();
    const selected = new Set(draft.selected_fact_ids);
    const facts = (profile.facts || []).filter((fact) => selected.has(fact.id));
    const groups = Object.groupBy
        ? Object.groupBy(facts, (fact) => fact.fact_type)
        : facts.reduce((result, fact) => ({ ...result, [fact.fact_type]: [...(result[fact.fact_type] || []), fact] }), {});
    const order = draft.section_config.order || SECTION_ORDER;
    const location = profile.location?.name || profile.location?.city;

    return (
        <div className={`resume-preview resume-preview--${draft.template_kind}`} aria-label={t("resumePreview.label")}>
            <header>
                {draft.template_kind === "photo" && <div className="resume-preview__photo"><i className="bi bi-person-fill" /><span>{draft.photo_asset_id ? t("resumePreview.photoReady") : t("resumePreview.photoMissing")}</span></div>}
                <div><h2>{profile.display_name}</h2><p>{profile.headline}</p></div>
                <address>
                    {draft.section_config.include_email && profile.email && <span>{profile.email}</span>}
                    {draft.section_config.include_phone && profile.phone && <span>{profile.phone}</span>}
                    {draft.section_config.include_location && location && <span>{location}</span>}
                </address>
            </header>
            {draft.section_config.include_summary && profile.summary && <section><h3>{t("resumePreview.summary")}</h3><p>{profile.summary}</p></section>}
            {order.map((type) => groups[type]?.length ? (
                <section key={type}><h3>{t(`resumeSection.${type}`) || SECTION_LABELS[type]}</h3>{groups[type].map((fact) => <ResumeFact key={fact.id} fact={fact} override={draft.content_overrides?.[fact.id]} t={t} />)}</section>
            ) : null)}
        </div>
    );
}
