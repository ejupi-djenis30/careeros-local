import { useEffect, useReducer, useRef, useState } from "react";
import { CanvasInspector } from "./CanvasInspector";
import { CanvasSection } from "./CanvasSection";
import { CanvasToolbar } from "./CanvasToolbar";
import { canvasReducer, createCanvasState } from "./canvasReducer";

export function ResumeCanvas({ document, templateKind, onChange, onPromoteClaim, promoting = false, photoUrl = null }) {
    const [state, dispatch] = useReducer(canvasReducer, document, createCanvasState);
    const [selection, setSelection] = useState(null);
    const [zoom, setZoom] = useState(0.85);
    const [pageCount, setPageCount] = useState(1);
    const mounted = useRef(false);
    const onChangeRef = useRef(onChange);
    const paperRef = useRef(null);

    useEffect(() => { onChangeRef.current = onChange; }, [onChange]);

    useEffect(() => {
        if (!mounted.current) {
            mounted.current = true;
            return;
        }
        onChangeRef.current(state.present);
    }, [state.present]);

    useEffect(() => {
        const paper = paperRef.current;
        if (!paper) return undefined;
        const measure = () => {
            const width = paper.getBoundingClientRect().width / zoom;
            if (!width) return;
            const pageHeight = width * 297 / 210;
            setPageCount(Math.max(1, Math.ceil(paper.scrollHeight / pageHeight)));
        };
        measure();
        if (typeof ResizeObserver === "undefined") return undefined;
        const observer = new ResizeObserver(measure);
        observer.observe(paper);
        return () => observer.disconnect();
    }, [state.present, zoom]);

    const selectedSection = state.present.sections.find((section) => section.id === selection?.sectionId);
    const selected = selectedSection?.blocks.find((block) => block.id === selection?.blockId) || null;
    const addClaim = () => {
        const blockId = `manual-${crypto.randomUUID()}`;
        dispatch({ type: "ADD_MANUAL_CLAIM", blockId });
        setSelection({ sectionId: "achievement", blockId });
    };

    return (
        <div className="resume-canvas-workspace">
            <CanvasToolbar state={state} templateKind={templateKind} dispatch={dispatch} onAddClaim={addClaim} zoom={zoom} onZoom={setZoom} pageCount={pageCount} />
            <CanvasInspector selected={selected} sectionId={selection?.sectionId} dispatch={dispatch} onPromote={onPromoteClaim} promoting={promoting} />
            <div className="resume-canvas-viewport">
                <div className="resume-canvas-stage" style={{ width: `${210 * zoom}mm`, minHeight: `${297 * zoom}mm`, "--canvas-accent": state.present.style.accent_color, "--canvas-font": state.present.style.font_family, "--canvas-size": `${state.present.style.base_font_size}pt`, "--canvas-leading": state.present.style.line_height, "--canvas-gap": `${state.present.style.section_spacing}pt`, "--canvas-margin": `${state.present.style.margin_mm}mm`, "--canvas-columns": state.present.style.columns }} aria-label="Canvas modificabile del CV">
                <div ref={paperRef} className={`resume-canvas-paper resume-canvas-paper--${templateKind} ${photoUrl ? "has-photo" : ""}`} style={{ transform: `scale(${zoom})` }} aria-label="Foglio A4 con guide pagina">
                    {templateKind === "photo" && photoUrl && <img className="canvas-profile-photo" src={photoUrl} alt="Foto profilo normalizzata" />}
                    <div className="resume-canvas-sections">{state.present.sections.map((section, index) => <CanvasSection key={section.id} section={section} index={index} total={state.present.sections.length} dispatch={dispatch} onSelect={(block, sectionId) => setSelection({ sectionId, blockId: block.id })} />)}</div>
                </div>
                </div>
            </div>
        </div>
    );
}
