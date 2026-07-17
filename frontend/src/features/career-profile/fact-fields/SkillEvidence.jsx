export function SkillEvidence({ selectedIds = [], options = [], onChange }) {
    const selected = new Set(selectedIds);
    const toggle = (id, enabled) => onChange(
        enabled ? [...selectedIds, id] : selectedIds.filter((item) => item !== id),
    );
    return (
        <fieldset className="fact-evidence">
            <legend>Evidenze della competenza</legend>
            {options.length === 0 ? <p>Aggiungi e salva altri fatti per collegarli come evidenza.</p> : options.map((option) => (
                <label className="check-line" key={option.id}>
                    <input type="checkbox" checked={selected.has(option.id)} onChange={(event) => toggle(option.id, event.target.checked)} aria-label={`Evidenza ${option.label}`} />
                    <span>{option.label}</span>
                    <small>{option.type}</small>
                </label>
            ))}
        </fieldset>
    );
}
