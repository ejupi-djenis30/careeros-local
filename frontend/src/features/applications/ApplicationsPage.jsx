import { useI18n } from "../../i18n/useI18n";
import { ApplicationAgenda } from "./ApplicationAgenda";
import { ApplicationDetailDialog } from "./ApplicationDetailDialog";
import { BOARD_STAGES, getStageLabels } from "./applicationModel";
import { CampaignImportPanel } from "./CampaignImportPanel";
import { CampaignFilters } from "./CampaignFilters";
import { useApplicationsWorkspace } from "./useApplicationsWorkspace";

function ApplicationCard({ application, onClick, locale, opening, expanded, buttonRef }) {
    return <button ref={buttonRef} type="button" className="application-card" onClick={onClick} disabled={opening} aria-busy={opening || undefined} aria-haspopup="dialog" aria-expanded={expanded}><strong>{application.title}</strong><span>{application.company}</span>{application.location && <small><i className="bi bi-geo-alt" /> {application.location}</small>}{application.next_action && <small className="application-card__next"><i className="bi bi-arrow-return-right" /> {application.next_action.title}</small>}<time dateTime={application.updated_at}>{new Date(application.updated_at).toLocaleDateString(locale)}</time></button>;
}

export function ApplicationsPage() {
    const { language, t } = useI18n();
    const {
        applications, campaigns, loading, error, resumeDrafts, resumeVersions,
        resumeMetadataStatus, retryResumeMetadata, selected, creating, showCreate,
        setShowCreate, openingId, agendaRevision, form, setForm, filters, setFilters,
        detailOpener, backgroundRef, addApplicationRef, applicationCardRefs,
        requestedApplicationId, filteredApplications, grouped, closed,
        handleCampaignImported, openApplication, closeApplication, create, handleChanged,
    } = useApplicationsWorkspace();
    const stageLabels = getStageLabels(t);
    const locale = language === "it" ? "it-IT" : "en-GB";

    if (loading) return <div className="page-loader" role="status"><span className="spinner-border" /><span>{t("applications.loading")}</span></div>;

    return (
        <div className="applications-workspace">
            <div ref={backgroundRef} className="applications-workspace__background">
            <div className="application-overview"><div><span>{t("applications.active")}</span><strong>{filteredApplications.length - closed}</strong></div><div><span>{t("applications.interviews")}</span><strong>{grouped.interview.length}</strong></div><div><span>{t("applications.offers")}</span><strong>{grouped.offer.length}</strong></div><div><span>{t("applications.closed")}</span><strong>{closed}</strong></div><button ref={addApplicationRef} type="button" className="button button--primary" onClick={() => setShowCreate((value) => !value)}><i className="bi bi-plus-lg" /> {t("applications.add")}</button></div>
            <CampaignImportPanel onImported={handleCampaignImported} />
            <CampaignFilters campaigns={campaigns} filters={filters} onChange={setFilters} />
            {error && <div className="inline-alert inline-alert--danger" role="alert">{error}</div>}
            {resumeMetadataStatus === "loading" && <div className="inline-alert" role="status">{t("applications.resumeMetadataLoading")}</div>}
            {resumeMetadataStatus === "error" && <div className="inline-alert inline-alert--danger" role="alert"><span>{t("applications.resumeMetadataError")}</span> <button type="button" className="button button--secondary" onClick={retryResumeMetadata}>{t("applications.resumeMetadataRetry")}</button></div>}
            {resumeMetadataStatus === "ready" && resumeVersions.length === 0 && <div className="inline-alert" role="status">{t("applications.resumeMetadataEmpty")}</div>}
            <ApplicationAgenda onOpen={openApplication} openingId={openingId} expandedId={selected?.id || ""} refreshKey={agendaRevision} />
            {showCreate && !requestedApplicationId && <form className="surface-section create-application" onSubmit={create}>
                <div className="section-heading"><div><span className="section-kicker">{t("applications.newSnapshot")}</span><h2>{t("applications.add")}</h2></div><button type="button" className="icon-button" onClick={() => setShowCreate(false)} aria-label={t("applications.close")}><i className="bi bi-x-lg" /></button></div>
                <div className="form-grid form-grid--3">
                    <label className="field-stack"><span>{t("applications.jobId")} <small>({t("applications.optional")})</small></span><input className="form-control" type="number" min="1" value={form.job_id} onChange={(e) => setForm({ ...form, job_id: e.target.value })} /></label>
                    <label className="field-stack"><span>{t("applications.initialStage")}</span><select className="form-select" value={form.initial_stage} onChange={(e) => setForm({ ...form, initial_stage: e.target.value })}>{["saved", "preparing", "applied"].map((stage) => <option key={stage} value={stage}>{stageLabels[stage]}</option>)}</select></label>
                    <label className="field-stack"><span>{t("applications.resumeVersion")}</span><select className="form-select" value={form.resume_version_id} disabled={resumeMetadataStatus !== "ready"} onChange={(e) => setForm({ ...form, resume_version_id: e.target.value })}><option value="">{resumeMetadataStatus === "loading" ? t("applications.resumeMetadataLoadingOption") : resumeMetadataStatus === "error" ? t("applications.resumeMetadataErrorOption") : t("applications.none")}</option>{resumeVersions.map((version) => <option key={version.id} value={version.id}>{version.label}</option>)}</select></label>
                </div>
                {!form.job_id && <>
                    <div className="form-grid form-grid--3">
                        <label className="field-stack"><span>{t("applications.title")}</span><input className="form-control" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} maxLength="240" required /></label>
                        <label className="field-stack"><span>{t("applications.company")}</span><input className="form-control" value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} maxLength="240" required /></label>
                        <label className="field-stack"><span>{t("applications.location")}</span><input className="form-control" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} maxLength="500" /></label>
                    </div>
                    <label className="field-stack"><span>{t("applications.jobUrl")}</span><input className="form-control" type="url" value={form.external_url} onChange={(e) => setForm({ ...form, external_url: e.target.value })} maxLength="2048" placeholder="https://…" /></label>
                    <label className="field-stack"><span>{t("applications.jobDescription")}</span><textarea className="form-control" rows="5" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} maxLength="100000" /></label>
                </>}
                <label className="field-stack"><span>{t("applications.initialNote")}</span><textarea className="form-control" rows="3" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></label>
                <button className="button button--primary" disabled={creating}>{creating ? t("applications.creating") : t("applications.create")}</button>
            </form>}
            {applications.length === 0 ? <div className="state-panel"><i className="bi bi-kanban" /><h2>{t("applications.emptyTitle")}</h2><p>{t("applications.emptyCopy")}</p><button className="button button--primary" onClick={() => setShowCreate(true)}>{t("applications.addFirst")}</button></div> : <div className="application-board">{BOARD_STAGES.map((stage) => <section key={stage} className="application-column"><header><span className={`stage-dot stage-dot--${stage}`} /><h2>{stageLabels[stage]}</h2><strong>{grouped[stage].length}</strong></header><div>{grouped[stage].map((application) => <ApplicationCard key={application.id} application={application} locale={locale} opening={openingId === application.id} expanded={selected?.id === application.id} buttonRef={(node) => { if (node) applicationCardRefs.current.set(application.id, node); else applicationCardRefs.current.delete(application.id); }} onClick={(event) => openApplication(application.id, event.currentTarget)} />)}{grouped[stage].length === 0 && <p className="application-column__empty">{t("applications.emptyColumn")}</p>}</div></section>)}{closed > 0 && <section className="application-column application-column--closed"><header><span className="stage-dot" /><h2>{t("applications.closed")}</h2><strong>{closed}</strong></header><div>{[...grouped.rejected, ...grouped.withdrawn, ...grouped.archived].map((application) => <ApplicationCard key={application.id} application={application} locale={locale} opening={openingId === application.id} expanded={selected?.id === application.id} buttonRef={(node) => { if (node) applicationCardRefs.current.set(application.id, node); else applicationCardRefs.current.delete(application.id); }} onClick={(event) => openApplication(application.id, event.currentTarget)} />)}</div></section>}</div>}
            </div>
            {selected && <ApplicationDetailDialog resumeDrafts={resumeDrafts} application={selected} resumeVersions={resumeVersions} resumeMetadataStatus={resumeMetadataStatus} onRetryResumeMetadata={retryResumeMetadata} onChanged={handleChanged} onClose={closeApplication} returnFocus={detailOpener} backgroundRef={backgroundRef} />}
        </div>
    );
}
