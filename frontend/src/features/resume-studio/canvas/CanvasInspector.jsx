export function CanvasInspector({ selected, sectionId, dispatch, onPromote, promoting }) {
    if (!selected) return <div className="canvas-inspector"><strong>Tracciabilità</strong><p>Seleziona un blocco per vedere la provenienza e i campi modificati.</p></div>;
    const ungrounded = selected.kind === "fact" && !selected.fact_ids?.length;
    return (
        <div className={`canvas-inspector ${ungrounded ? "is-ungrounded" : ""}`} aria-live="polite">
            <strong>{selected.kind === "identity" ? "Identità del profilo" : ungrounded ? "Claim senza fonte" : "Claim collegato"}</strong>
            {selected.fact_ids?.length > 0 && <p><i className="bi bi-link-45deg" /> {selected.fact_ids.length} fatto/i del Career Vault</p>}
            <p>{ungrounded ? "Salvalo nel profilo prima di pubblicare." : selected.manual_fields?.length ? `Modifiche manuali: ${selected.manual_fields.join(", ")}` : "Testo sincronizzato con il profilo"}</p>
            <label className="canvas-inspector__field"><span>Spazio prima</span><input aria-label="Spazio prima del blocco" type="number" min="0" max="24" value={selected.layout?.spacing_before_pt ?? 0} onChange={(event) => dispatch({ type: "SET_BLOCK_LAYOUT", sectionId, blockId: selected.id, field: "spacing_before_pt", value: event.target.value })} /></label>
            <label className="check-line canvas-inspector__check"><input aria-label="Mantieni blocco unito" type="checkbox" checked={selected.layout?.keep_together ?? true} onChange={(event) => dispatch({ type: "SET_BLOCK_LAYOUT", sectionId, blockId: selected.id, field: "keep_together", value: event.target.checked })} /> Non spezzare</label>
            {ungrounded && <button type="button" className="button button--secondary" onClick={() => onPromote(selected.id)} disabled={promoting || !selected.content.title.trim()}>{promoting ? "Salvataggio…" : "Salva nel Career Vault"}</button>}
        </div>
    );
}
