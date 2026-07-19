import { CanvasBlock } from "./CanvasBlock";
import { useI18n } from "../../../i18n/useI18n";

export function CanvasSection({ section, index, total, dispatch, onSelect }) {
    const { t } = useI18n();
    const drop = (event, toIndex) => {
        event.preventDefault();
        event.stopPropagation();
        const raw = event.dataTransfer.getData("application/x-careeros-block");
        if (raw) {
            const source = JSON.parse(raw);
            if (source.sectionId === section.id) dispatch({ type: "MOVE_BLOCK", sectionId: section.id, blockId: source.blockId, toIndex });
        }
    };
    return (
        <section className={`canvas-section canvas-section--${section.kind} ${section.visible ? "" : "is-hidden"} ${section.page_break_before ? "has-page-break" : ""}`} draggable onDragStart={(event) => event.dataTransfer.setData("application/x-careeros-section", section.id)} onDragOver={(event) => event.preventDefault()} onDrop={(event) => {
            const sectionId = event.dataTransfer.getData("application/x-careeros-section");
            if (sectionId) dispatch({ type: "MOVE_SECTION", sectionId, toIndex: index });
        }}>
            <div className="canvas-section__controls">
                <span className="canvas-drag" aria-hidden="true"><i className="bi bi-grip-horizontal" /></span>
                <button type="button" className="icon-button" disabled={index === 0} onClick={() => dispatch({ type: "MOVE_SECTION", sectionId: section.id, direction: -1 })} aria-label={t("canvas.sectionUp", { title: section.title })}><i className="bi bi-arrow-up" /></button>
                <button type="button" className="icon-button" disabled={index === total - 1} onClick={() => dispatch({ type: "MOVE_SECTION", sectionId: section.id, direction: 1 })} aria-label={t("canvas.sectionDown", { title: section.title })}><i className="bi bi-arrow-down" /></button>
                <button type="button" className="icon-button" onClick={() => dispatch({ type: "SET_SECTION_VISIBLE", sectionId: section.id, visible: !section.visible })} aria-label={t(section.visible ? "canvas.hideSection" : "canvas.showSection", { title: section.title })}><i className={`bi ${section.visible ? "bi-eye" : "bi-eye-slash"}`} /></button>
                {section.kind !== "identity" && <button type="button" className={`icon-button ${section.page_break_before ? "is-active" : ""}`} onClick={() => dispatch({ type: "SET_PAGE_BREAK", sectionId: section.id, enabled: !section.page_break_before })} aria-label={t("canvas.pageBreak", { title: section.title })}><i className="bi bi-file-break" /></button>}
            </div>
            {section.kind !== "identity" && <input className="canvas-inline canvas-inline--section" aria-label={t("canvas.sectionTitle", { kind: section.kind })} value={section.title} onChange={(event) => dispatch({ type: "SET_SECTION_TITLE", sectionId: section.id, title: event.target.value })} />}
            <div className="canvas-section__blocks">{section.blocks.map((block, blockIndex) => <div key={block.id} onDragOver={(event) => event.preventDefault()} onDrop={(event) => drop(event, blockIndex)}><CanvasBlock block={block} sectionId={section.id} index={blockIndex} total={section.blocks.length} dispatch={dispatch} onSelect={onSelect} /></div>)}</div>
        </section>
    );
}
