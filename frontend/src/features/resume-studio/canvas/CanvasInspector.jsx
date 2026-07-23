import { useI18n } from "../../../i18n/useI18n";

export function CanvasInspector({ selected, sectionId, dispatch, onPromote, promoting }) {
    const { t } = useI18n();
    if (!selected) return <div className="canvas-inspector"><strong>{t("canvas.traceability")}</strong><p>{t("canvas.selectBlock")}</p></div>;
    const ungrounded = selected.kind === "fact" && !selected.fact_ids?.length;
    return (
        <div className={`canvas-inspector ${ungrounded ? "is-ungrounded" : ""}`} aria-live="polite">
            <strong>{selected.kind === "identity" ? t("canvas.profileIdentity") : ungrounded ? t("canvas.ungrounded") : t("canvas.grounded")}</strong>
            {selected.fact_ids?.length > 0 && <p><i className="bi bi-link-45deg" /> {selected.fact_ids.length} {t("canvas.vaultFacts")}</p>}
            <p>{ungrounded ? t("canvas.saveBeforePublish") : selected.manual_fields?.length ? t("canvas.manualChanges", { fields: selected.manual_fields.join(", ") }) : t("canvas.synced")}</p>
            <label className="canvas-inspector__field"><span>{t("canvas.spaceBefore")}</span><input aria-label={t("canvas.spaceBeforeControl")} type="number" min="0" max="24" value={selected.layout?.spacing_before_pt ?? 0} onChange={(event) => dispatch({ type: "SET_BLOCK_LAYOUT", sectionId, blockId: selected.id, field: "spacing_before_pt", value: event.target.value })} /></label>
            <label className="check-line canvas-inspector__check"><input aria-label={t("canvas.keepTogether")} type="checkbox" checked={selected.layout?.keep_together ?? true} onChange={(event) => dispatch({ type: "SET_BLOCK_LAYOUT", sectionId, blockId: selected.id, field: "keep_together", value: event.target.checked })} /> {t("canvas.doNotSplit")}</label>
            {ungrounded && <button type="button" className="button button--secondary" onClick={() => onPromote(selected.id)} disabled={promoting || !selected.content.title.trim()}>{promoting ? t("profile.saving") : t("canvas.saveToVault")}</button>}
        </div>
    );
}
