import { useI18n } from "../../i18n/useI18n";

export function DossierTarget({ application, binding, onBindingChange, resumeDrafts, resumeVersions,
    publishVersionId, onPublishVersionChange, busy, onRefresh, onRequest }) {
    const { t } = useI18n();
    const linked = resumeVersions.find((version) => version.id === application.resume_version_id);
    const resumeId = binding.resume_draft_id || linked?.draft_id;
    const query = new URLSearchParams({ kind: "materials", application_id: application.id });
    if (resumeId) query.set("resume_id", resumeId);
    const targetValue = binding.resume_draft_id ? `draft:${binding.resume_draft_id}`
        : binding.resume_version_id ? `version:${binding.resume_version_id}` : "";
    const versions = resumeVersions.filter((version) => version.draft_id === binding.resume_draft_id
        && version.draft_revision === binding.expected_resume_draft_revision);
    return <div className="dossier-material-target">
        <p className="dossier-disclaimer">{t("dossier.unsent")}</p>
        {resumeDrafts.length > 0 && <label className="field-stack"><span>{t("dossier.targetResume")}</span>
            <select className="form-select" value={targetValue} disabled={busy} onChange={(event) => {
                const [kind, id] = event.target.value.split(":");
                const draft = resumeDrafts.find((item) => item.id === id);
                onBindingChange(kind === "draft" && draft
                    ? { resume_draft_id: draft.id, expected_resume_draft_revision: draft.revision }
                    : { resume_version_id: id || null });
            }}>
                <option value="">{t("dossier.chooseResume")}</option>
                {application.resume_version_id && <option value={`version:${application.resume_version_id}`}>{linked?.label || t("dossier.linkedPublication")}</option>}
                {resumeDrafts.map((draft) => <option key={draft.id} value={`draft:${draft.id}`}>{draft.title} · {t("dossier.resumeDraftRevision", { revision: draft.revision })}</option>)}
            </select>
        </label>}
        <div className="dossier-material-actions">
            <a className="button button--secondary" href={`/agent-work?${query}`} aria-disabled={busy || undefined}
                onClick={(event) => { if (busy) event.preventDefault(); else onRequest(event); }}>{t("dossier.requestMaterials")}</a>
            <button type="button" className="button button--secondary" disabled={busy} onClick={onRefresh}>{t("dossier.refreshMaterials")}</button>
        </div>
        {binding.resume_draft_id && <div className="dossier-publication-target">
            <p>{t("dossier.publishResumeFirst")}</p>
            <a href={`/resumes?resumeId=${encodeURIComponent(binding.resume_draft_id)}`}>{t("dossier.openResume")}</a>
            <label className="field-stack"><span>{t("dossier.approvedVersion")}</span>
                <select className="form-select" value={publishVersionId} disabled={busy} onChange={(event) => onPublishVersionChange(event.target.value)}>
                    <option value="">{t("dossier.chooseApprovedVersion")}</option>
                    {versions.map((version) => <option key={version.id} value={version.id}>{version.label}</option>)}
                </select>
            </label>
        </div>}
    </div>;
}
