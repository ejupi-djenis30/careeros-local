import { FACT_LABELS, factTitle } from "../career-profile/profileModel";

export function ResumeFactSelector({ facts, selectedIds, onChange }) {
    const selected = new Set(selectedIds);
    const toggle = (id) => onChange(selected.has(id) ? selectedIds.filter((item) => item !== id) : [...selectedIds, id]);
    return (
        <div className="resume-fact-selector">
            {facts.map((fact) => (
                <label key={fact.id} className={`resume-fact-option ${selected.has(fact.id) ? "is-selected" : ""}`}>
                    <input type="checkbox" checked={selected.has(fact.id)} onChange={() => toggle(fact.id)} />
                    <span><small>{FACT_LABELS[fact.fact_type]}</small><strong>{factTitle(fact)}</strong></span>
                    <span className={`verification verification--${fact.verification_status}`}>{fact.verification_status}</span>
                </label>
            ))}
        </div>
    );
}

