import { useI18n } from "../../../i18n/useI18n";

const splitList = (value) => value.split(",").map((item) => item.trim()).filter(Boolean);
const ACTION_KINDS = ["research", "networking", "learning", "portfolio", "application", "interview", "other"];

export function GoalActions({ actions = [], evidenceOptions = [], resumeVersions = [], onChange }) {
    const { t } = useI18n();
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
        id: crypto.randomUUID(), title: "", kind: "other", status: "planned", due_date: "", notes: "",
        linked_fact_ids: [], linked_job_ids: [], linked_application_ids: [],
        linked_learning_activity_ids: [], linked_resume_version_ids: [], learning_resource_url: "",
    }]);

    return (
        <section className="goal-subsection" aria-label={t("goal.actions")}>
            <div className="goal-subsection__heading"><strong>{t("goal.actionPlan")}</strong><button type="button" className="button button--ghost" onClick={add}>{t("goal.addAction")}</button></div>
            {actions.length === 0 && <p className="goal-empty">{t("goal.actionsEmpty")}</p>}
            {actions.map((action, index) => (
                <article className="goal-action" key={action.id}>
                    <div className="goal-action__main">
                        <label className="field-stack"><span>{t("goal.actionNumber", { index: index + 1 })}</span><input className="form-control" value={action.title} onChange={(event) => update(index, { title: event.target.value })} /></label>
                        <label className="field-stack"><span>{t("goal.actionType")}</span><select className="form-select" value={action.kind || "other"} onChange={(event) => update(index, { kind: event.target.value })}>{ACTION_KINDS.map((kind) => <option key={kind} value={kind}>{t(`goal.actionKind.${kind}`)}</option>)}</select></label>
                        <label className="field-stack"><span>{t("goal.actionStatus")}</span><select className="form-select" value={action.status || "planned"} onChange={(event) => setStatus(index, action, event.target.value)}><option value="planned">{t("goal.status.planned")}</option><option value="in_progress">{t("goal.status.inProgress")}</option><option value="completed">{t("goal.status.completed")}</option><option value="cancelled">{t("goal.status.cancelled")}</option></select></label>
                        <label className="field-stack"><span>{t("goal.actionDue")}</span><input className="form-control" type="date" value={action.due_date || ""} onChange={(event) => update(index, { due_date: event.target.value })} /></label>
                        <button type="button" className="icon-button icon-button--danger" onClick={() => onChange(actions.filter((_, position) => position !== index))} aria-label={t("goal.removeAction", { index: index + 1 })}><i className="bi bi-trash3" /></button>
                    </div>
                    <div className="form-grid form-grid--2">
                        <label className="field-stack"><span>{t("goal.actionNotes")}</span><textarea className="form-control" rows="2" maxLength="3000" value={action.notes || ""} onChange={(event) => update(index, { notes: event.target.value })} /></label>
                        <label className="field-stack"><span>{t("goal.learningResource")}</span><input className="form-control" type="url" value={action.learning_resource_url || ""} onChange={(event) => update(index, { learning_resource_url: event.target.value })} placeholder="https://" /></label>
                        <label className="field-stack"><span>{t("goal.linkedJobs")}</span><input className="form-control" value={(action.linked_job_ids || []).join(", ")} onChange={(event) => update(index, { linked_job_ids: splitList(event.target.value) })} /></label>
                        <label className="field-stack"><span>{t("goal.linkedApplications")}</span><input className="form-control" value={(action.linked_application_ids || []).join(", ")} onChange={(event) => update(index, { linked_application_ids: splitList(event.target.value) })} /></label>
                    </div>
                    {evidenceOptions.length > 0 && <fieldset className="fact-evidence"><legend>{t("goal.linkedEvidence")}</legend>{evidenceOptions.map((option) => <label className="check-line" key={option.id}><input type="checkbox" checked={(action.linked_fact_ids || []).includes(option.id)} onChange={(event) => toggleEvidence(index, action, option.id, event.target.checked)} aria-label={t("goal.actionEvidence", { index: index + 1, label: option.label })} /><span>{option.label}</span><small>{option.type}</small></label>)}</fieldset>}
                    {actions.some((item) => item.kind === "learning" && item.id !== action.id) && <fieldset className="fact-evidence"><legend>{t("goal.linkedLearning")}</legend>{actions.filter((item) => item.kind === "learning" && item.id !== action.id).map((learning) => { const title = learning.title || t("goal.untitledActivity"); return <label className="check-line" key={learning.id}><input type="checkbox" checked={(action.linked_learning_activity_ids || []).includes(learning.id)} onChange={(event) => toggleLink(index, action, "linked_learning_activity_ids", learning.id, event.target.checked)} aria-label={t("goal.learningActivity", { index: index + 1, title })} /><span>{title}</span><small>{t("goal.learning")}</small></label>; })}</fieldset>}
                    {resumeVersions.length > 0 && <fieldset className="fact-evidence"><legend>{t("goal.linkedResumes")}</legend>{resumeVersions.map((version) => <label className="check-line" key={version.id}><input type="checkbox" checked={(action.linked_resume_version_ids || []).includes(version.id)} onChange={(event) => toggleLink(index, action, "linked_resume_version_ids", version.id, event.target.checked)} aria-label={t("goal.resumeVersion", { index: index + 1, title: version.draft_title, version: version.semantic_version })} /><span>{version.draft_title}</span><small>{version.semantic_version}</small></label>)}</fieldset>}
                </article>
            ))}
        </section>
    );
}
