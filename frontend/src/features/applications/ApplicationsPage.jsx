import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ApplicationService } from "../../services/applications";
import { ResumeService } from "../../services/resumes";
import { useToast } from "../../context/ToastContext";
import { useI18n } from "../../i18n/useI18n";
import { ApplicationDetailDialog } from "./ApplicationDetailDialog";
import { BOARD_STAGES, STAGES, getStageLabels } from "./applicationModel";

function ApplicationCard({ application, onClick, locale, opening, expanded }) {
    return <button type="button" className="application-card" onClick={onClick} disabled={opening} aria-busy={opening || undefined} aria-haspopup="dialog" aria-expanded={expanded}><strong>{application.title}</strong><span>{application.company}</span>{application.location && <small><i className="bi bi-geo-alt" /> {application.location}</small>}{application.next_action && <small className="application-card__next"><i className="bi bi-arrow-return-right" /> {application.next_action.title}</small>}<time dateTime={application.updated_at}>{new Date(application.updated_at).toLocaleDateString(locale)}</time></button>;
}

const emptyForm = (jobId = "") => ({
    job_id: jobId, title: "", company: "", location: "", external_url: "", description: "",
    initial_stage: "saved", resume_version_id: "", note: "",
});

export function ApplicationsPage() {
    const { language, t } = useI18n();
    const [searchParams, setSearchParams] = useSearchParams();
    const { showToast } = useToast();
    const [applications, setApplications] = useState([]);
    const [selected, setSelected] = useState(null);
    const [resumeVersions, setResumeVersions] = useState([]);
    const [resumeMetadataStatus, setResumeMetadataStatus] = useState("loading");
    const [resumeMetadataRevision, setResumeMetadataRevision] = useState(0);
    const [loading, setLoading] = useState(true);
    const [creating, setCreating] = useState(false);
    const [error, setError] = useState("");
    const [showCreate, setShowCreate] = useState(searchParams.has("jobId"));
    const [openingId, setOpeningId] = useState("");
    const [form, setForm] = useState(emptyForm(searchParams.get("jobId") || ""));
    const applicationRequestRef = useRef({ controller: null, id: 0 });
    const detailRequestRef = useRef({ controller: null, id: 0 });
    const [detailOpener, setDetailOpener] = useState(null);
    const backgroundRef = useRef(null);
    const addApplicationRef = useRef(null);
    const stageLabels = getStageLabels(t);
    const locale = language === "it" ? "it-IT" : "en-GB";

    const requestApplications = useCallback(() => {
        const requestId = applicationRequestRef.current.id + 1;
        applicationRequestRef.current.controller?.abort();
        const controller = new AbortController();
        applicationRequestRef.current = { controller, id: requestId };

        return ApplicationService.list({ signal: controller.signal })
            .then((items) => {
                if (controller.signal.aborted || applicationRequestRef.current.id !== requestId) return;
                setApplications(Array.isArray(items) ? items : []);
                setError("");
            })
            .catch((loadError) => {
                if (controller.signal.aborted || loadError?.name === "AbortError" || applicationRequestRef.current.id !== requestId) return;
                setError(loadError.message);
            })
            .finally(() => {
                if (!controller.signal.aborted && applicationRequestRef.current.id === requestId) {
                    applicationRequestRef.current.controller = null;
                    setLoading(false);
                }
            });
    }, []);

    useEffect(() => {
        void requestApplications();
        return () => {
            applicationRequestRef.current.id += 1;
            applicationRequestRef.current.controller?.abort();
            applicationRequestRef.current.controller = null;
            detailRequestRef.current.id += 1;
            detailRequestRef.current.controller?.abort();
            detailRequestRef.current.controller = null;
        };
    }, [requestApplications]);
    useEffect(() => {
        const controller = new AbortController();
        ResumeService.list({ signal: controller.signal })
            .then((items) => Promise.all(items.map((item) => ResumeService.get(item.id, { signal: controller.signal }))))
            .then((drafts) => {
                if (controller.signal.aborted) return;
                setResumeVersions(drafts.flatMap((draft) => draft.versions.map((version) => ({ id: version.id, label: `${draft.title} · v${version.semantic_version}`, selected_fact_ids: version.selected_fact_ids || [] }))));
                setResumeMetadataStatus("ready");
            })
            .catch((loadError) => {
                if (controller.signal.aborted || loadError?.name === "AbortError") return;
                setResumeMetadataStatus("error");
            });
        return () => controller.abort();
    }, [resumeMetadataRevision]);

    const retryResumeMetadata = () => {
        setResumeMetadataStatus("loading");
        setResumeMetadataRevision((current) => current + 1);
    };

    const grouped = useMemo(() => Object.fromEntries(STAGES.map((stage) => [stage, applications.filter((item) => item.current_stage === stage)])), [applications]);
    const closed = grouped.rejected.length + grouped.withdrawn.length + grouped.archived.length;

    const openApplication = async (id, opener) => {
        const requestId = detailRequestRef.current.id + 1;
        detailRequestRef.current.controller?.abort();
        const controller = new AbortController();
        detailRequestRef.current = { controller, id: requestId };
        setError("");
        setOpeningId(id);
        try {
            const detail = await ApplicationService.get(id, { signal: controller.signal });
            if (controller.signal.aborted || detailRequestRef.current.id !== requestId) return;
            setDetailOpener(opener);
            setSelected(detail);
        } catch (loadError) {
            if (!controller.signal.aborted && detailRequestRef.current.id === requestId) setError(loadError.message);
        } finally {
            if (detailRequestRef.current.id === requestId) {
                detailRequestRef.current.controller = null;
                setOpeningId("");
            }
        }
    };

    const create = async (event) => {
        event.preventDefault();
        setCreating(true);
        setError("");
        try {
            const jobSource = form.job_id
                ? { job_id: Number(form.job_id) }
                : { manual_job: {
                    title: form.title.trim(), company: form.company.trim(),
                    location: form.location.trim() || null,
                    external_url: form.external_url.trim() || null,
                    description: form.description.trim() || null,
                } };
            const application = await ApplicationService.create({
                ...jobSource,
                initial_stage: form.initial_stage,
                resume_version_id: form.resume_version_id || null,
                note: form.note.trim() || null,
            });
            await requestApplications();
            setDetailOpener(addApplicationRef.current);
            setSelected(application);
            setShowCreate(false);
            setSearchParams({});
            setForm(emptyForm());
            showToast({ messageKey: "applications.added" }, "success");
        } catch (createError) {
            setError(createError.message);
        } finally {
            setCreating(false);
        }
    };

    const handleChanged = (updated) => {
        setSelected(updated);
        void requestApplications();
    };

    if (loading) return <div className="page-loader" role="status"><span className="spinner-border" /><span>{t("applications.loading")}</span></div>;

    return (
        <div className="applications-workspace">
            <div ref={backgroundRef} className="applications-workspace__background">
            <div className="application-overview"><div><span>{t("applications.active")}</span><strong>{applications.length - closed}</strong></div><div><span>{t("applications.interviews")}</span><strong>{grouped.interview.length}</strong></div><div><span>{t("applications.offers")}</span><strong>{grouped.offer.length}</strong></div><div><span>{t("applications.closed")}</span><strong>{closed}</strong></div><button ref={addApplicationRef} type="button" className="button button--primary" onClick={() => setShowCreate((value) => !value)}><i className="bi bi-plus-lg" /> {t("applications.add")}</button></div>
            {error && <div className="inline-alert inline-alert--danger" role="alert">{error}</div>}
            {resumeMetadataStatus === "loading" && <div className="inline-alert" role="status">{t("applications.resumeMetadataLoading")}</div>}
            {resumeMetadataStatus === "error" && <div className="inline-alert inline-alert--danger" role="alert"><span>{t("applications.resumeMetadataError")}</span> <button type="button" className="button button--secondary" onClick={retryResumeMetadata}>{t("applications.resumeMetadataRetry")}</button></div>}
            {resumeMetadataStatus === "ready" && resumeVersions.length === 0 && <div className="inline-alert" role="status">{t("applications.resumeMetadataEmpty")}</div>}
            {showCreate && <form className="surface-section create-application" onSubmit={create}>
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
            {applications.length === 0 ? <div className="state-panel"><i className="bi bi-kanban" /><h2>{t("applications.emptyTitle")}</h2><p>{t("applications.emptyCopy")}</p><button className="button button--primary" onClick={() => setShowCreate(true)}>{t("applications.addFirst")}</button></div> : <div className="application-board">{BOARD_STAGES.map((stage) => <section key={stage} className="application-column"><header><span className={`stage-dot stage-dot--${stage}`} /><h2>{stageLabels[stage]}</h2><strong>{grouped[stage].length}</strong></header><div>{grouped[stage].map((application) => <ApplicationCard key={application.id} application={application} locale={locale} opening={openingId === application.id} expanded={selected?.id === application.id} onClick={(event) => openApplication(application.id, event.currentTarget)} />)}{grouped[stage].length === 0 && <p className="application-column__empty">{t("applications.emptyColumn")}</p>}</div></section>)}{closed > 0 && <section className="application-column application-column--closed"><header><span className="stage-dot" /><h2>{t("applications.closed")}</h2><strong>{closed}</strong></header><div>{[...grouped.rejected, ...grouped.withdrawn, ...grouped.archived].map((application) => <ApplicationCard key={application.id} application={application} locale={locale} opening={openingId === application.id} expanded={selected?.id === application.id} onClick={(event) => openApplication(application.id, event.currentTarget)} />)}</div></section>}</div>}
            </div>
            {selected && <ApplicationDetailDialog application={selected} resumeVersions={resumeVersions} resumeMetadataStatus={resumeMetadataStatus} onRetryResumeMetadata={retryResumeMetadata} onChanged={handleChanged} onClose={() => setSelected(null)} returnFocus={detailOpener} backgroundRef={backgroundRef} />}
        </div>
    );
}
