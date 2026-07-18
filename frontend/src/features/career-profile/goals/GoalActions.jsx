const splitList = (value) => value.split(",").map((item) => item.trim()).filter(Boolean);

export function GoalActions({ actions = [], evidenceOptions = [], resumeVersions = [], onChange }) {
    const update = (index, patch) => onChange(actions.map((action, position) => (
        position === index ? { ...action, ...patch } : action
    )));
    const setStatus = (index, action, status) => update(index, {
        status,
        completed_date: status === "completed"
            ? (action.completed_date || new Date().toISOString().slice(0, 10))
            : null,
    });
    const toggleEvidence = (index, action, factId, enabled) => update(index, {
        linked_fact_ids: enabled
            ? [...new Set([...(action.linked_fact_ids || []), factId])]
            : (action.linked_fact_ids || []).filter((item) => item !== factId),
    });
    const toggleLink = (index, action, field, id, enabled) => update(index, {
        [field]: enabled
            ? [...new Set([...(action[field] || []), id])]
            : (action[field] || []).filter((item) => item !== id),
    });
    const add = () => onChange([...actions, {
        id: crypto.randomUUID(),
        title: "",
        kind: "other",
        status: "planned",
        due_date: "",
        notes: "",
        linked_fact_ids: [],
        linked_job_ids: [],
        linked_application_ids: [],
        linked_learning_activity_ids: [],
        linked_resume_version_ids: [],
        learning_resource_url: "",
    }]);

    return (
        <section className="goal-subsection" aria-label="Azioni obiettivo">
            <div className="goal-subsection__heading"><strong>Piano d’azione</strong><button type="button" className="button button--ghost" onClick={add}>Aggiungi azione</button></div>
            {actions.length === 0 && <p className="goal-empty">Trasforma l’obiettivo in prossime azioni concrete e verificabili.</p>}
            {actions.map((action, index) => (
                <article className="goal-action" key={action.id}>
                    <div className="goal-action__main">
                        <label className="field-stack"><span>Azione {index + 1}</span><input className="form-control" value={action.title} onChange={(event) => update(index, { title: event.target.value })} /></label>
                        <label className="field-stack"><span>Tipo azione</span><select className="form-select" value={action.kind || "other"} onChange={(event) => update(index, { kind: event.target.value })}><option value="research">Ricerca</option><option value="networking">Networking</option><option value="learning">Formazione</option><option value="portfolio">Portfolio</option><option value="application">Candidatura</option><option value="interview">Colloquio</option><option value="other">Altro</option></select></label>
                        <label className="field-stack"><span>Stato azione</span><select className="form-select" value={action.status || "planned"} onChange={(event) => setStatus(index, action, event.target.value)}><option value="planned">Pianificata</option><option value="in_progress">In corso</option><option value="completed">Completata</option><option value="cancelled">Annullata</option></select></label>
                        <label className="field-stack"><span>Scadenza azione</span><input className="form-control" type="date" value={action.due_date || ""} onChange={(event) => update(index, { due_date: event.target.value })} /></label>
                        <button type="button" className="icon-button icon-button--danger" onClick={() => onChange(actions.filter((_, position) => position !== index))} aria-label={`Rimuovi azione ${index + 1}`}><i className="bi bi-trash3" /></button>
                    </div>
                    <div className="form-grid form-grid--2">
                        <label className="field-stack"><span>Note azione</span><textarea className="form-control" rows="2" maxLength="3000" value={action.notes || ""} onChange={(event) => update(index, { notes: event.target.value })} /></label>
                        <label className="field-stack"><span>Risorsa formativa</span><input className="form-control" type="url" value={action.learning_resource_url || ""} onChange={(event) => update(index, { learning_resource_url: event.target.value })} placeholder="https://" /></label>
                        <label className="field-stack"><span>ID opportunità collegate</span><input className="form-control" value={(action.linked_job_ids || []).join(", ")} onChange={(event) => update(index, { linked_job_ids: splitList(event.target.value) })} /></label>
                        <label className="field-stack"><span>ID candidature collegate</span><input className="form-control" value={(action.linked_application_ids || []).join(", ")} onChange={(event) => update(index, { linked_application_ids: splitList(event.target.value) })} /></label>
                    </div>
                    {evidenceOptions.length > 0 && <fieldset className="fact-evidence"><legend>Evidenze collegate all’azione</legend>{evidenceOptions.map((option) => <label className="check-line" key={option.id}><input type="checkbox" checked={(action.linked_fact_ids || []).includes(option.id)} onChange={(event) => toggleEvidence(index, action, option.id, event.target.checked)} aria-label={`Evidenza azione ${index + 1} ${option.label}`} /><span>{option.label}</span><small>{option.type}</small></label>)}</fieldset>}
                    {actions.some((item) => item.kind === "learning" && item.id !== action.id) && <fieldset className="fact-evidence"><legend>Attività formative collegate</legend>{actions.filter((item) => item.kind === "learning" && item.id !== action.id).map((learning) => <label className="check-line" key={learning.id}><input type="checkbox" checked={(action.linked_learning_activity_ids || []).includes(learning.id)} onChange={(event) => toggleLink(index, action, "linked_learning_activity_ids", learning.id, event.target.checked)} aria-label={`Attività formativa azione ${index + 1} ${learning.title || "senza titolo"}`} /><span>{learning.title || "Attività senza titolo"}</span><small>Formazione</small></label>)}</fieldset>}
                    {resumeVersions.length > 0 && <fieldset className="fact-evidence"><legend>Versioni CV collegate</legend>{resumeVersions.map((version) => <label className="check-line" key={version.id}><input type="checkbox" checked={(action.linked_resume_version_ids || []).includes(version.id)} onChange={(event) => toggleLink(index, action, "linked_resume_version_ids", version.id, event.target.checked)} aria-label={`Versione CV azione ${index + 1} ${version.draft_title} ${version.semantic_version}`} /><span>{version.draft_title}</span><small>{version.semantic_version}</small></label>)}</fieldset>}
                </article>
            ))}
        </section>
    );
}
