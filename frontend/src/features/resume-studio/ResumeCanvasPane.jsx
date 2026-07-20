import { ResumePreview } from "./ResumePreview";
import { ResumeCanvas } from "./canvas/ResumeCanvas";
import { useProfilePhotoUrl } from "./canvas/useProfilePhotoUrl";
import { useI18n } from "../../i18n/useI18n";

export function ResumeCanvasPane({ profile, draft, dirty, onChange, onPromoteClaim, promoting }) {
    const { t } = useI18n();
    const photoUrl = useProfilePhotoUrl(draft.template_kind === "photo" ? draft.photo_asset_id : null);
    return (
        <aside className="resume-preview-pane resume-canvas-pane" aria-label={t("resume.canvasEditor")}>
            <div className="resume-preview-pane__header"><span>{t("resume.canvas")}</span><small>{dirty ? t("resume.canvasUnsaved") : t("resume.canvasSaved")}</small></div>
            {draft.canvas_document ? <ResumeCanvas key={`${draft.id || "new"}-${draft.template_kind}`} document={draft.canvas_document} templateKind={draft.template_kind} onChange={onChange} onPromoteClaim={onPromoteClaim} promoting={promoting} photoUrl={photoUrl} /> : <div className="canvas-empty"><ResumePreview profile={profile} draft={draft} /><p>{t("resume.canvasEmpty")}</p></div>}
        </aside>
    );
}
