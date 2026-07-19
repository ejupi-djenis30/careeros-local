import { Link } from "react-router-dom";
import { useI18n } from "../../i18n/useI18n";
import { ResumeFactSelector } from "./ResumeFactSelector";
import { ResumeVersions } from "./ResumeVersions";
import { ResumeCanvasPane } from "./ResumeCanvasPane";
import { ResumeLibrary } from "./ResumeLibrary";
import { ResumeSettings } from "./ResumeSettings";
import { ResumeSyncPanel } from "./ResumeSyncPanel";
import { useResumeStudio } from "./useResumeStudio";

export function ResumeStudioPage() {
    const { t } = useI18n();
    const studio = useResumeStudio();
    const { profile, resumes, draft, dirty, loading, busy, error, profileMissing } = studio;
    if (loading) return <div className="page-loader" role="status"><span className="spinner-border" /><span>{t("resume.loading")}</span></div>;
    if (profileMissing) return <div className="state-panel"><i className="bi bi-person-vcard" /><h2>{t("resume.profileFirst")}</h2><p>{t("resume.profileFirstCopy")}</p><Link className="button button--primary" to="/profile">{t("resume.openVault")}</Link></div>;
    if (!profile || !draft) return <div className="state-panel state-panel--danger"><h2>{t("resume.unavailable")}</h2><p>{error}</p><button className="button button--secondary" onClick={studio.initialize}>{t("profile.retry")}</button></div>;
    return (
        <div className="resume-studio">
            <ResumeLibrary resumes={resumes} draft={draft} onLoad={studio.loadDraft} onNew={studio.startNew} />
            <div className="resume-editor">
                {error && <div className="inline-alert inline-alert--danger" role="alert"><div><strong>{t("resume.operationFailed")}</strong><span>{error}</span></div></div>}
                <ResumeSettings studio={studio} />
                {studio.syncPreview && <ResumeSyncPanel preview={studio.syncPreview} selected={studio.syncSelection} onSelected={studio.setSyncSelection} onApply={() => studio.applySync("apply")} onReset={() => studio.applySync("reset")} onClose={studio.closeSync} busy={busy} />}
                <section className="surface-section"><div className="section-heading"><div><span className="section-kicker">{t("resume.explicitSelection")}</span><h2>{t("resume.factsInResume")} <span>{draft.selected_fact_ids.length}</span></h2></div></div><p className="section-intro">{t("resume.selectionCopy")}</p><ResumeFactSelector facts={profile.facts} selectedIds={draft.selected_fact_ids} onChange={(selected_fact_ids) => studio.changeDraft({ selected_fact_ids })} /></section>
                <section className="surface-section"><div className="section-heading"><div><span className="section-kicker">{t("resume.immutableVersions")}</span><h2>{t("resume.publications")}</h2></div></div><ResumeVersions versions={draft.versions} comparison={studio.versionComparison} busy={busy} onCompare={studio.compareVersions} onRestore={studio.restoreVersion} onError={studio.setError} /></section>
            </div>
            <ResumeCanvasPane profile={profile} draft={draft} dirty={dirty} onChange={(canvas_document) => studio.changeDraft({ canvas_document })} onPromoteClaim={studio.promoteClaim} promoting={busy === "promote-claim"} />
        </div>
    );
}
