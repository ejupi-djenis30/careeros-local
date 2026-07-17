import { useEffect, useReducer, useRef, useState } from "react";
import { CanvasInspector } from "./CanvasInspector";
import { CanvasSection } from "./CanvasSection";
import { CanvasToolbar } from "./CanvasToolbar";
import { canvasReducer, createCanvasState } from "./canvasReducer";

export function ResumeCanvas({ document, templateKind, onChange, onPromoteClaim, promoting = false, photoUrl = null }) {
    const [state, dispatch] = useReducer(canvasReducer, document, createCanvasState);
    const [selectedId, setSelectedId] = useState(null);
    const mounted = useRef(false);
    const onChangeRef = useRef(onChange);

    useEffect(() => { onChangeRef.current = onChange; }, [onChange]);

    useEffect(() => {
        if (!mounted.current) {
            mounted.current = true;
            return;
        }
        onChangeRef.current(state.present);
    }, [state.present]);

    const selected = state.present.sections.flatMap((section) => section.blocks)
        .find((block) => block.id === selectedId) || null;
    const addClaim = () => {
        const blockId = `manual-${crypto.randomUUID()}`;
        dispatch({ type: "ADD_MANUAL_CLAIM", blockId });
        setSelectedId(blockId);
    };

    return (
        <div className="resume-canvas-workspace">
            <CanvasToolbar state={state} templateKind={templateKind} dispatch={dispatch} onAddClaim={addClaim} />
            <CanvasInspector selected={selected} onPromote={onPromoteClaim} promoting={promoting} />
            <div className="resume-canvas-viewport">
                <div className={`resume-canvas-paper resume-canvas-paper--${templateKind} ${photoUrl ? "has-photo" : ""}`} style={{ "--canvas-accent": state.present.style.accent_color, "--canvas-font": state.present.style.font_family, "--canvas-size": `${state.present.style.base_font_size}pt`, "--canvas-leading": state.present.style.line_height, "--canvas-gap": `${state.present.style.section_spacing}pt`, "--canvas-margin": `${state.present.style.margin_mm}mm`, "--canvas-columns": state.present.style.columns }} aria-label="Canvas modificabile del CV">
                    {templateKind === "photo" && photoUrl && <img className="canvas-profile-photo" src={photoUrl} alt="Foto profilo normalizzata" />}
                    <div className="resume-canvas-sections">{state.present.sections.map((section, index) => <CanvasSection key={section.id} section={section} index={index} total={state.present.sections.length} dispatch={dispatch} onSelect={(block) => setSelectedId(block.id)} />)}</div>
                </div>
            </div>
        </div>
    );
}
