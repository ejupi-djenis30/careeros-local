import { useState } from "react";
import { FactEditor } from "./FactEditor";
import { FACT_TYPES, factTitle, newFact } from "./profileModel";

export function FactsEditor({ facts, onChange }) {
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
                <div><span className="section-kicker">Base verificabile</span><h2 id="facts-title">Fatti di carriera <span>{facts.length}</span></h2></div>
                <div className="button-cluster">
                    <select className="form-select form-select-sm" value={newType} onChange={(e) => setNewType(e.target.value)} aria-label="Tipo di fatto da aggiungere">{FACT_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
                    <button type="button" className="button button--secondary" onClick={add}><i className="bi bi-plus-lg" /> Aggiungi</button>
                </div>
            </div>
            <p className="section-intro">Il coach e i CV possono usare solo elementi presenti qui. Conferma i fatti che hai verificato personalmente.</p>
            <div className="fact-list">
                {facts.length === 0 ? <div className="empty-inline"><p>Aggiungi esperienze, competenze e risultati: diventano la fonte unica per ogni documento.</p></div> : facts.map((fact, index) => (
                    <FactEditor key={fact.id || fact.clientKey} fact={fact} index={index} total={facts.length} evidenceOptions={facts.filter((item) => item.id && item.id !== fact.id).map((item) => ({ id: item.id, label: factTitle(item), type: FACT_TYPES.find(([value]) => value === item.fact_type)?.[1] || item.fact_type }))} onChange={(next) => update(index, next)} onRemove={() => onChange(facts.filter((_, position) => position !== index))} onMove={move} />
                ))}
            </div>
        </section>
    );
}
