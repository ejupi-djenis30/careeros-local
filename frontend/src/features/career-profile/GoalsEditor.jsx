import { FACT_LABELS, factTitle, newGoal } from "./profileModel";
import { GoalDetails } from "./goals/GoalDetails";
import { GoalProgress } from "./goals/GoalProgress";

export function GoalsEditor({ goals, facts = [], resumeVersions = [], onChange }) {
    const evidenceOptions = facts.filter((fact) => fact.id).map((fact) => ({ id: fact.id, label: factTitle(fact), type: FACT_LABELS[fact.fact_type] || fact.fact_type }));
    const updateGoal = (index, next) => onChange(
        goals.map((goal, position) => position === index ? next : goal),
    );
    const removeGoal = (index) => onChange(goals.filter((_, position) => position !== index));
    const setPrimary = (index) => onChange(
        goals.map((goal, position) => ({ ...goal, is_primary: position === index })),
    );

    return (
        <section className="surface-section" aria-labelledby="goals-title">
            <div className="section-heading">
                <div><span className="section-kicker">Direzione</span><h2 id="goals-title">Obiettivi di carriera</h2></div>
                <button type="button" className="button button--secondary" onClick={() => onChange([...goals, newGoal()])}><i className="bi bi-plus-lg" /> Aggiungi</button>
            </div>
            {goals.length === 0 ? (
                <div className="empty-inline"><p>Nessun obiettivo definito. Imposta una direzione per personalizzare CV e piano di crescita.</p></div>
            ) : goals.map((goal, index) => (
                <article className="goal-card" key={goal.id || goal.clientKey}>
                    <div className="goal-card__header">
                        <input className="form-control" value={goal.name} onChange={(event) => updateGoal(index, { ...goal, name: event.target.value })} aria-label={`Nome obiettivo ${index + 1}`} />
                        <label className="check-line"><input type="radio" name="primary-goal" checked={goal.is_primary} onChange={() => setPrimary(index)} /> Primario</label>
                        <button type="button" className="icon-button icon-button--danger" onClick={() => removeGoal(index)} aria-label={`Rimuovi ${goal.name}`}><i className="bi bi-trash3" /></button>
                    </div>
                    <GoalDetails payload={goal.payload} onChange={(payload) => updateGoal(index, { ...goal, payload })} />
                    <GoalProgress payload={goal.payload} evidenceOptions={evidenceOptions} resumeVersions={resumeVersions} onChange={(payload) => updateGoal(index, { ...goal, payload })} />
                </article>
            ))}
        </section>
    );
}
