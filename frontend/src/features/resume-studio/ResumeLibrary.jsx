import { useI18n } from "../../i18n/useI18n";

export function ResumeLibrary({ resumes, draft, onLoad, onNew }) {
    const { t } = useI18n();
    return (
        <aside className="resume-library" aria-label={t("resume.library")}>
            <div className="resume-library__heading"><div><span>{resumes.length}</span><strong>{t("resume.drafts")}</strong></div><button type="button" className="icon-button icon-button--accent" onClick={onNew} aria-label={t("resume.new")}><i className="bi bi-plus-lg" /></button></div>
            <div className="resume-library__list">{resumes.map((resume) => <button type="button" key={resume.id} className={`resume-library__item ${draft.id === resume.id ? "is-active" : ""}`} onClick={() => onLoad(resume.id)}><span className={`template-icon template-icon--${resume.template_kind}`}><i className={`bi ${resume.template_kind === "ats" ? "bi-file-text" : "bi-person-bounding-box"}`} /></span><span><strong>{resume.title}</strong><small>{resume.latest_version ? `v${resume.latest_version}` : t("resume.draftOnly")} · {resume.selected_fact_count} {t("resume.factCount")}</small></span></button>)}</div>
            <div className="resume-library__note"><i className="bi bi-shield-check" /><span>{t("resume.hashNote")}</span></div>
        </aside>
    );
}
