import { FACT_LABELS, factTitle } from "./profileModel";
import { DetailedFactFields } from "./fact-fields/DetailedFactFields";

export function FactEditor({ fact, index, total, evidenceOptions, onChange, onRemove, onMove }) {
    const update = (field, value) => onChange({
        ...fact,
        payload: { ...fact.payload, [field]: value },
    });

    return (
        <details className="fact-card" open={fact.id == null}>
            <summary>
                <span className="fact-card__type">{FACT_LABELS[fact.fact_type]}</span>
                <strong>{factTitle(fact)}</strong>
                <span className={`verification verification--${fact.verification_status}`}>
                    {fact.verification_status}
                </span>
            </summary>
            <div className="fact-card__body">
                <DetailedFactFields type={fact.fact_type} payload={fact.payload} update={update} evidenceOptions={evidenceOptions} />
                <div className="fact-card__footer">
                    <label className="field-stack field-stack--inline">
                        <span>Stato</span>
                        <select className="form-select form-select-sm" value={fact.verification_status} onChange={(event) => onChange({ ...fact, verification_status: event.target.value })}>
                            <option value="draft">Bozza</option>
                            <option value="confirmed">Confermato</option>
                            <option value="imported">Importato</option>
                        </select>
                    </label>
                    <div className="button-cluster">
                        <button type="button" className="icon-button" disabled={index === 0} onClick={() => onMove(index, -1)} aria-label="Sposta su"><i className="bi bi-arrow-up" /></button>
                        <button type="button" className="icon-button" disabled={index === total - 1} onClick={() => onMove(index, 1)} aria-label="Sposta giù"><i className="bi bi-arrow-down" /></button>
                        <button type="button" className="button button--danger-subtle" onClick={onRemove}><i className="bi bi-trash3" /> Rimuovi</button>
                    </div>
                </div>
            </div>
        </details>
    );
}
