import { SECTION_LABELS } from "./resumeModel";
import { useI18n } from "../../i18n/useI18n";

export function ResumeSyncPanel({ preview, selected, onSelected, onApply, onReset, onClose, busy }) {
    const { t } = useI18n();
    const label = (kind) => kind === "summary"
        ? t("resumeSync.summary")
        : kind === "identity"
            ? t("resumeSync.identity")
            : t(`resumeSection.${kind}`) || SECTION_LABELS[kind] || kind;
    const toggle = (kind) => onSelected(
        selected.includes(kind) ? selected.filter((item) => item !== kind) : [...selected, kind],
    );
    return (
        <section className="resume-sync-panel" aria-labelledby="resume-sync-title">
            <div className="section-heading">
                <div><span className="section-kicker">{t("resumeSync.kicker", { from: preview.source_profile_revision, to: preview.current_profile_revision })}</span><h2 id="resume-sync-title">{t("resumeSync.title")}</h2></div>
                <button type="button" className="icon-button" onClick={onClose} aria-label={t("resumeSync.close")}><i className="bi bi-x-lg" /></button>
            </div>
            <p className="section-intro">{t("resumeSync.copy")}</p>
            <div className="resume-sync-list">{preview.sections.map((section) => (
                <label key={section.kind} className={selected.includes(section.kind) ? "is-selected" : ""}>
                    <input type="checkbox" checked={selected.includes(section.kind)} onChange={() => toggle(section.kind)} aria-label={t("resumeSync.syncSection", { section: label(section.kind) })} />
                    <span><strong>{label(section.kind)}</strong><small>+{section.added_fact_ids.length} · −{section.removed_fact_ids.length} · {t("resumeSync.changed", { count: section.changed_fact_ids.length })}</small></span>
                    {section.conflicts.length > 0 && <em><i className="bi bi-shield-exclamation" /> {t("resumeSync.protected", { count: section.conflicts.length })}</em>}
                </label>
            ))}</div>
            {preview.preserved_manual_fields.length > 0 && <p className="sync-preserved"><i className="bi bi-lock" /> {t("resumeSync.preserved", { count: preview.preserved_manual_fields.length })}</p>}
            <div className="button-cluster"><button type="button" className="button button--danger-subtle" onClick={onReset} disabled={Boolean(busy)}>{t("resumeSync.reset")}</button><button type="button" className="button button--primary" onClick={onApply} disabled={Boolean(busy) || !selected.length}>{busy === "sync" ? t("resumeSync.syncing") : t("resumeSync.apply")}</button></div>
        </section>
    );
}
