export function ResumeLibrary({ resumes, draft, onLoad, onNew }) {
    return (
        <aside className="resume-library">
            <div className="resume-library__heading"><div><span>{resumes.length}</span><strong>Bozze</strong></div><button type="button" className="icon-button icon-button--accent" onClick={onNew} aria-label="Nuovo CV"><i className="bi bi-plus-lg" /></button></div>
            <div className="resume-library__list">{resumes.map((resume) => <button type="button" key={resume.id} className={`resume-library__item ${draft.id === resume.id ? "is-active" : ""}`} onClick={() => onLoad(resume.id)}><span className={`template-icon template-icon--${resume.template_kind}`}><i className={`bi ${resume.template_kind === "ats" ? "bi-file-text" : "bi-person-bounding-box"}`} /></span><span><strong>{resume.title}</strong><small>{resume.latest_version ? `v${resume.latest_version}` : "Solo bozza"} · {resume.selected_fact_count} fatti</small></span></button>)}</div>
            <div className="resume-library__note"><i className="bi bi-shield-check" /><span>Gli artefatti sono immutabili e accompagnati da hash SHA-256.</span></div>
        </aside>
    );
}
