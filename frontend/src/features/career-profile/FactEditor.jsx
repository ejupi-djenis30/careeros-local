import { FACT_LABELS, factTitle } from "./profileModel";
import { DetailedFactFields } from "./fact-fields/DetailedFactFields";
import { useI18n } from "../../i18n/useI18n";

export function FactEditor({ fact, index, total, evidenceOptions, evidenceState, onChange, onRemove, onMove }) {
    const { t } = useI18n();
    const update = (field, value) => onChange({
        ...fact,
        payload: { ...fact.payload, [field]: value },
    });

    return (
        <details className="fact-card" open={fact.id == null}>
            <summary>
                <span className="fact-card__type">{t(`fact.type.${fact.fact_type}`) || FACT_LABELS[fact.fact_type]}</span>
                <strong>{factTitle(fact)}</strong>
                <span className={`verification verification--${fact.verification_status}`}>
                    {fact.verification_status}
                </span>
            </summary>
            <div className="fact-card__body">
                <DetailedFactFields type={fact.fact_type} payload={fact.payload} update={update} evidenceOptions={evidenceOptions} />
                <div className="fact-card__footer">
                    <div className="fact-provenance">
                    <label className="field-stack field-stack--inline">
                        <span>{t("facts.status")}</span>
                        <select className="form-select form-select-sm" value={fact.verification_status} onChange={(event) => onChange({ ...fact, verification_status: event.target.value })}>
                            <option value="draft">{t("facts.status.draft")}</option>
                            <option value="confirmed">{t("facts.status.confirmed")}</option>
                            <option value="imported">{t("facts.status.imported")}</option>
                        </select>
                    </label>
                    {evidenceState && <span className={`evidence-state evidence-state--${evidenceState.state}`}><i className="bi bi-link-45deg" /> {t(`facts.evidence.${evidenceState.state}`)}</span>}
                    </div>
                    <div className="button-cluster">
                        <button type="button" className="icon-button" disabled={index === 0} onClick={() => onMove(index, -1)} aria-label={t("facts.moveUp")}><i className="bi bi-arrow-up" /></button>
                        <button type="button" className="icon-button" disabled={index === total - 1} onClick={() => onMove(index, 1)} aria-label={t("facts.moveDown")}><i className="bi bi-arrow-down" /></button>
                        <button type="button" className="button button--danger-subtle" onClick={onRemove}><i className="bi bi-trash3" /> {t("facts.remove")}</button>
                    </div>
                </div>
            </div>
        </details>
    );
}
