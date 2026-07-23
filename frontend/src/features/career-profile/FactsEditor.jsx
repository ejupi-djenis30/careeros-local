import { useState } from "react";
import { FactEditor } from "./FactEditor";
import { FACT_TYPES, factTitle, newFact } from "./profileModel";
import { useI18n } from "../../i18n/useI18n";

export function FactsEditor({ facts, analysis, onChange }) {
    const { t } = useI18n();
    const [newType, setNewType] = useState("experience");
    const update = (index, fact) => onChange(facts.map((item, position) => position === index ? fact : item));
    const move = (index, direction) => {
        const target = index + direction;
        if (target < 0 || target >= facts.length) return;
        const next = [...facts];
        [next[index], next[target]] = [next[target], next[index]];
        onChange(next.map((fact, position) => ({ ...fact, position })));
    };
    const add = () => onChange([...facts, { ...newFact(newType), position: facts.length }]);

    return (
        <section className="surface-section" aria-labelledby="facts-title">
            <div className="section-heading section-heading--wrap">
                <div><span className="section-kicker">{t("facts.kicker")}</span><h2 id="facts-title">{t("facts.title")} <span>{facts.length}</span></h2></div>
                <div className="button-cluster">
                    <select className="form-select form-select-sm" value={newType} onChange={(e) => setNewType(e.target.value)} aria-label={t("facts.addType")}>{FACT_TYPES.map(([value]) => <option key={value} value={value}>{t(`fact.type.${value}`)}</option>)}</select>
                    <button type="button" className="button button--secondary" onClick={add}><i className="bi bi-plus-lg" /> {t("facts.add")}</button>
                </div>
            </div>
            <p className="section-intro">{t("facts.copy")}</p>
            <div className="fact-list">
                {facts.length === 0 ? <div className="empty-inline"><p>{t("facts.empty")}</p></div> : facts.map((fact, index) => (
                    <FactEditor key={fact.id || fact.clientKey} fact={fact} index={index} total={facts.length} evidenceOptions={facts.filter((item) => item.id && item.id !== fact.id).map((item) => ({ id: item.id, label: factTitle(item), type: t(`fact.type.${item.fact_type}`) }))} evidenceState={analysis?.evidence?.find((item) => item.fact_id === fact.id)} onChange={(next) => update(index, next)} onRemove={() => onChange(facts.filter((_, position) => position !== index))} onMove={move} />
                ))}
            </div>
        </section>
    );
}
