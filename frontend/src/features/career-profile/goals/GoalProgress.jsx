import { ProgressNotes } from "./ProgressNotes";
import { GoalActions } from "./GoalActions";

const LEVELS = ["none", "learning", "working", "advanced", "expert"];

export function GoalProgress({ payload, evidenceOptions = [], resumeVersions = [], onChange }) {
    const gaps = payload.skill_gaps || [];
    const milestones = payload.milestones || [];
    const updateGap = (index, patch) => onChange({ ...payload, skill_gaps: gaps.map((item, position) => position === index ? { ...item, ...patch } : item) });
    const updateMilestone = (index, patch) => onChange({ ...payload, milestones: milestones.map((item, position) => position === index ? { ...item, ...patch } : item) });
    return (
        <div className="goal-progress">
            <section className="goal-subsection" aria-label="Gap di competenze">
                <div className="goal-subsection__heading"><strong>Gap di competenze</strong><button type="button" className="button button--ghost" onClick={() => onChange({ ...payload, skill_gaps: [...gaps, { clientKey: crypto.randomUUID(), skill: "", current_level: "learning", target_level: "working", action: "" }] })}>Aggiungi gap</button></div>
                {gaps.map((gap, index) => <div className="goal-progress__row" key={gap.clientKey || index}><label className="field-stack"><span>Competenza gap {index + 1}</span><input className="form-control" value={gap.skill} onChange={(event) => updateGap(index, { skill: event.target.value })} /></label><label className="field-stack"><span>Livello attuale</span><select className="form-select" value={gap.current_level} onChange={(event) => updateGap(index, { current_level: event.target.value })}>{LEVELS.map((level) => <option key={level}>{level}</option>)}</select></label><label className="field-stack"><span>Livello target</span><select className="form-select" value={gap.target_level} onChange={(event) => updateGap(index, { target_level: event.target.value })}>{LEVELS.slice(1).map((level) => <option key={level}>{level}</option>)}</select></label><label className="field-stack"><span>Azione</span><input className="form-control" value={gap.action || ""} onChange={(event) => updateGap(index, { action: event.target.value })} /></label><button type="button" className="icon-button icon-button--danger" onClick={() => onChange({ ...payload, skill_gaps: gaps.filter((_, position) => position !== index) })} aria-label={`Rimuovi gap ${index + 1}`}><i className="bi bi-trash3" /></button></div>)}
            </section>
            <section className="goal-subsection" aria-label="Milestone obiettivo">
                <div className="goal-subsection__heading"><strong>Milestone</strong><button type="button" className="button button--ghost" onClick={() => onChange({ ...payload, milestones: [...milestones, { id: crypto.randomUUID(), title: "", status: "planned", target_date: "" }] })}>Aggiungi milestone</button></div>
                {milestones.map((milestone, index) => <div className="goal-progress__row" key={milestone.id}><label className="field-stack"><span>Milestone {index + 1}</span><input className="form-control" value={milestone.title} onChange={(event) => updateMilestone(index, { title: event.target.value })} /></label><label className="field-stack"><span>Stato milestone</span><select className="form-select" value={milestone.status} onChange={(event) => updateMilestone(index, { status: event.target.value, completed_date: event.target.value === "achieved" ? (milestone.completed_date || new Date().toISOString().slice(0, 10)) : null })}><option value="planned">Pianificata</option><option value="in_progress">In corso</option><option value="achieved">Raggiunta</option><option value="cancelled">Annullata</option></select></label><label className="field-stack"><span>Scadenza milestone</span><input className="form-control" type="date" value={milestone.target_date || ""} onChange={(event) => updateMilestone(index, { target_date: event.target.value })} /></label><button type="button" className="icon-button icon-button--danger" onClick={() => onChange({ ...payload, milestones: milestones.filter((_, position) => position !== index) })} aria-label={`Rimuovi milestone ${index + 1}`}><i className="bi bi-trash3" /></button></div>)}
            </section>
            <GoalActions actions={payload.actions || []} evidenceOptions={evidenceOptions} resumeVersions={resumeVersions} onChange={(actions) => onChange({ ...payload, actions })} />
            <ProgressNotes notes={payload.progress_notes || []} onChange={(progress_notes) => onChange({ ...payload, progress_notes })} />
        </div>
    );
}
