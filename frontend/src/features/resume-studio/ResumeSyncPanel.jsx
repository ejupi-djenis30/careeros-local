import { SECTION_LABELS } from "./resumeModel";

const label = (kind) => kind === "summary" ? "Sintesi" : kind === "identity" ? "Identità" : (SECTION_LABELS[kind] || kind);

export function ResumeSyncPanel({ preview, selected, onSelected, onApply, onReset, onClose, busy }) {
    const toggle = (kind) => onSelected(
        selected.includes(kind) ? selected.filter((item) => item !== kind) : [...selected, kind],
    );
    return (
        <section className="resume-sync-panel" aria-labelledby="resume-sync-title">
            <div className="section-heading">
                <div><span className="section-kicker">Revisione profilo {preview.source_profile_revision} → {preview.current_profile_revision}</span><h2 id="resume-sync-title">Sincronizzazione selettiva</h2></div>
                <button type="button" className="icon-button" onClick={onClose} aria-label="Chiudi sincronizzazione"><i className="bi bi-x-lg" /></button>
            </div>
            <p className="section-intro">Scegli cosa aggiornare. Le sezioni escluse e i campi modificati manualmente restano invariati.</p>
            <div className="resume-sync-list">{preview.sections.map((section) => (
                <label key={section.kind} className={selected.includes(section.kind) ? "is-selected" : ""}>
                    <input type="checkbox" checked={selected.includes(section.kind)} onChange={() => toggle(section.kind)} aria-label={`Sincronizza ${label(section.kind)}`} />
                    <span><strong>{label(section.kind)}</strong><small>+{section.added_fact_ids.length} · −{section.removed_fact_ids.length} · {section.changed_fact_ids.length} modificati</small></span>
                    {section.conflicts.length > 0 && <em><i className="bi bi-shield-exclamation" /> {section.conflicts.length} override protetti</em>}
                </label>
            ))}</div>
            {preview.preserved_manual_fields.length > 0 && <p className="sync-preserved"><i className="bi bi-lock" /> {preview.preserved_manual_fields.length} campi manuali saranno preservati.</p>}
            <div className="button-cluster"><button type="button" className="button button--danger-subtle" onClick={onReset} disabled={Boolean(busy)}>Rigenera tutto</button><button type="button" className="button button--primary" onClick={onApply} disabled={Boolean(busy) || !selected.length}>{busy === "sync" ? "Sincronizzo…" : "Applica selezione"}</button></div>
        </section>
    );
}
