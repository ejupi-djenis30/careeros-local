export function CanvasToolbar({ state, templateKind, dispatch, onAddClaim, zoom, onZoom, pageCount }) {
    const style = state.present.style;
    const setStyle = (field, value) => dispatch({ type: "SET_STYLE", field, value });
    return (
        <div className="canvas-toolbar" aria-label="Strumenti canvas CV">
            <div className="button-cluster">
                <button type="button" className="icon-button" onClick={() => dispatch({ type: "UNDO" })} disabled={!state.past.length} aria-label="Annulla modifica"><i className="bi bi-arrow-counterclockwise" /></button>
                <button type="button" className="icon-button" onClick={() => dispatch({ type: "REDO" })} disabled={!state.future.length} aria-label="Ripeti modifica"><i className="bi bi-arrow-clockwise" /></button>
                <button type="button" className="button button--ghost canvas-add-claim" onClick={onAddClaim}><i className="bi bi-plus-lg" /> Nuovo claim</button>
            </div>
            <label><span>Font</span><select value={style.font_family} onChange={(event) => setStyle("font_family", event.target.value)}><option>Helvetica</option><option>Arial</option><option>Georgia</option></select></label>
            <label><span>Corpo {style.base_font_size} pt</span><input aria-label="Dimensione testo" type="range" min="9" max="12" step="0.5" value={style.base_font_size} onChange={(event) => setStyle("base_font_size", Number(event.target.value))} /></label>
            <label><span>Interlinea {style.line_height}</span><input type="range" min="1" max="1.6" step="0.1" value={style.line_height} onChange={(event) => setStyle("line_height", Number(event.target.value))} /></label>
            <label><span>Spaziatura {style.section_spacing}</span><input type="range" min="4" max="24" value={style.section_spacing} onChange={(event) => setStyle("section_spacing", Number(event.target.value))} /></label>
            <label><span>Margini {style.margin_mm} mm</span><input type="range" min="10" max="30" value={style.margin_mm} onChange={(event) => setStyle("margin_mm", Number(event.target.value))} /></label>
            <label><span>Accento</span><input aria-label="Colore accento" type="color" value={style.accent_color} onChange={(event) => setStyle("accent_color", event.target.value)} /></label>
            <label><span>Zoom {Math.round(zoom * 100)}%</span><input aria-label="Zoom canvas" type="range" min="0.5" max="1.5" step="0.05" value={zoom} onChange={(event) => onZoom(Number(event.target.value))} /></label>
            {templateKind === "photo" && <label><span>Colonne</span><select value={style.columns} onChange={(event) => setStyle("columns", Number(event.target.value))}><option value="1">Una</option><option value="2">Due</option></select></label>}
            {templateKind === "ats" && <span className="canvas-toolbar__badge"><i className="bi bi-shield-check" /> ATS · 1 colonna</span>}
            <span className={`canvas-toolbar__badge ${pageCount > 3 ? "is-warning" : ""}`} aria-live="polite"><i className="bi bi-file-earmark" /> {pageCount} {pageCount === 1 ? "pagina" : "pagine"}</span>
        </div>
    );
}
