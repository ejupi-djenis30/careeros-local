import { ResumePreview } from "./ResumePreview";
import { ResumeCanvas } from "./canvas/ResumeCanvas";
import { useProfilePhotoUrl } from "./canvas/useProfilePhotoUrl";

export function ResumeCanvasPane({ profile, draft, dirty, onChange, onPromoteClaim, promoting }) {
    const photoUrl = useProfilePhotoUrl(draft.template_kind === "photo" ? draft.photo_asset_id : null);
    return (
        <aside className="resume-preview-pane resume-canvas-pane" aria-label="Editor canvas CV">
            <div className="resume-preview-pane__header"><span>Canvas CV</span><small>{dirty ? "Modifiche non salvate" : "Salvato localmente"}</small></div>
            {draft.canvas_document ? <ResumeCanvas key={`${draft.id || "new"}-${draft.revision || 0}-${draft.template_kind}`} document={draft.canvas_document} templateKind={draft.template_kind} onChange={onChange} onPromoteClaim={onPromoteClaim} promoting={promoting} photoUrl={photoUrl} /> : <div className="canvas-empty"><ResumePreview profile={profile} draft={draft} /><p>Usa “Crea automaticamente” o salva la bozza per attivare il canvas modificabile.</p></div>}
        </aside>
    );
}
