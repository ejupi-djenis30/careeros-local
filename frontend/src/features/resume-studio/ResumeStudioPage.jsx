import { Link } from "react-router-dom";
import { ResumeFactSelector } from "./ResumeFactSelector";
import { ResumeVersions } from "./ResumeVersions";
import { ResumeCanvasPane } from "./ResumeCanvasPane";
import { ResumeLibrary } from "./ResumeLibrary";
import { ResumeSettings } from "./ResumeSettings";
import { ResumeSyncPanel } from "./ResumeSyncPanel";
import { useResumeStudio } from "./useResumeStudio";

export function ResumeStudioPage() {
    const studio = useResumeStudio();
    const { profile, resumes, draft, dirty, loading, busy, error, profileMissing } = studio;
    if (loading) return <div className="page-loader" role="status"><span className="spinner-border" /><span>Preparo CV Studio…</span></div>;
    if (profileMissing) return <div className="state-panel"><i className="bi bi-person-vcard" /><h2>Prima crea il Career Vault</h2><p>I CV sono derivati esclusivamente dai tuoi fatti verificati.</p><Link className="button button--primary" to="/profile">Apri Career Vault</Link></div>;
    if (!profile || !draft) return <div className="state-panel state-panel--danger"><h2>CV Studio non disponibile</h2><p>{error}</p><button className="button button--secondary" onClick={studio.initialize}>Riprova</button></div>;
    return (
        <div className="resume-studio">
            <ResumeLibrary resumes={resumes} draft={draft} onLoad={studio.loadDraft} onNew={studio.startNew} />
            <div className="resume-editor">
                {error && <div className="inline-alert inline-alert--danger" role="alert"><div><strong>Operazione non riuscita</strong><span>{error}</span></div></div>}
                <ResumeSettings studio={studio} />
                {studio.syncPreview && <ResumeSyncPanel preview={studio.syncPreview} selected={studio.syncSelection} onSelected={studio.setSyncSelection} onApply={() => studio.applySync("apply")} onReset={() => studio.applySync("reset")} onClose={studio.closeSync} busy={busy} />}
                <section className="surface-section"><div className="section-heading"><div><span className="section-kicker">Selezione esplicita</span><h2>Fatti nel CV <span>{draft.selected_fact_ids.length}</span></h2></div></div><p className="section-intro">Una versione pubblicata fotografa esattamente questa selezione e la revisione corrente del profilo.</p><ResumeFactSelector facts={profile.facts} selectedIds={draft.selected_fact_ids} onChange={(selected_fact_ids) => studio.changeDraft({ selected_fact_ids })} /></section>
                <section className="surface-section"><div className="section-heading"><div><span className="section-kicker">Versioni immutabili</span><h2>Pubblicazioni</h2></div></div><ResumeVersions versions={draft.versions} comparison={studio.versionComparison} busy={busy} onCompare={studio.compareVersions} onRestore={studio.restoreVersion} onError={studio.setError} /></section>
            </div>
            <ResumeCanvasPane profile={profile} draft={draft} dirty={dirty} onChange={(canvas_document) => studio.changeDraft({ canvas_document })} onPromoteClaim={studio.promoteClaim} promoting={busy === "promote-claim"} />
        </div>
    );
}
