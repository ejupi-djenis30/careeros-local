import { useI18n } from "../../../i18n/useI18n";

const lines = (value) => value.split("\n").map((item) => item.trim()).filter(Boolean);

export function CanvasBlock({ block, sectionId, index, total, dispatch, onSelect }) {
    const { t } = useI18n();
    const update = (field, value) => dispatch({ type: "UPDATE_BLOCK", sectionId, blockId: block.id, field, value });
    const layout = { spacing_before_pt: 0, keep_together: true, ...(block.layout || {}) };
    return (
        <article className={`canvas-block ${block.visible ? "" : "is-hidden"}`} style={{ marginTop: `${layout.spacing_before_pt}pt`, breakInside: layout.keep_together ? "avoid" : "auto" }} draggable onDragStart={(event) => { event.stopPropagation(); event.dataTransfer.setData("application/x-careeros-block", JSON.stringify({ sectionId, blockId: block.id })); }} onClick={() => onSelect(block, sectionId)}>
            <div className="canvas-block__controls">
                <span className="canvas-drag" aria-hidden="true"><i className="bi bi-grip-vertical" /></span>
                <button type="button" className="icon-button" disabled={index === 0} onClick={() => dispatch({ type: "MOVE_BLOCK", sectionId, blockId: block.id, direction: -1 })} aria-label={t("canvas.blockUp", { title: block.content.title || t("canvas.block") })}><i className="bi bi-arrow-up" /></button>
                <button type="button" className="icon-button" disabled={index === total - 1} onClick={() => dispatch({ type: "MOVE_BLOCK", sectionId, blockId: block.id, direction: 1 })} aria-label={t("canvas.blockDown", { title: block.content.title || t("canvas.block") })}><i className="bi bi-arrow-down" /></button>
                <button type="button" className="icon-button" onClick={() => dispatch({ type: "SET_BLOCK_VISIBLE", sectionId, blockId: block.id, visible: !block.visible })} aria-label={t(block.visible ? "canvas.hideBlock" : "canvas.showBlock", { title: block.content.title || t("canvas.block") })}><i className={`bi ${block.visible ? "bi-eye" : "bi-eye-slash"}`} /></button>
                {block.kind === "fact" && !block.fact_ids.length && <button type="button" className="icon-button" onClick={() => dispatch({ type: "REMOVE_BLOCK", sectionId, blockId: block.id })} aria-label={t("canvas.removeClaim", { title: block.content.title || t("canvas.manual") })}><i className="bi bi-trash3" /></button>}
            </div>
            <input className="canvas-inline canvas-inline--title" aria-label={t("canvas.blockTitle", { index: index + 1 })} value={block.content.title} onChange={(event) => update("title", event.target.value)} />
            <input className="canvas-inline canvas-inline--subtitle" aria-label={t("canvas.blockSubtitle", { index: index + 1 })} value={block.content.subtitle} onChange={(event) => update("subtitle", event.target.value)} />
            {block.content.date_range && <input className="canvas-inline canvas-inline--date" aria-label={t("canvas.blockPeriod", { index: index + 1 })} value={block.content.date_range} onChange={(event) => update("date_range", event.target.value)} />}
            <textarea className="canvas-inline canvas-inline--description" aria-label={t("canvas.blockDescription", { index: index + 1 })} rows="2" value={block.content.description} onChange={(event) => update("description", event.target.value)} />
            {(block.content.bullets.length > 0 || block.kind === "fact") && <textarea className="canvas-inline canvas-inline--bullets" aria-label={t("canvas.blockBullets", { index: index + 1 })} rows={Math.max(2, block.content.bullets.length)} value={block.content.bullets.join("\n")} onChange={(event) => update("bullets", lines(event.target.value))} />}
        </article>
    );
}
