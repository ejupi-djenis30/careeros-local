import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApplicationService } from "../../services/applications";
import { useI18n } from "../../i18n/useI18n";

function initialForm(application) {
    const snapshot = application.job_snapshot || {};
    return {
        title: snapshot.title || "",
        company: snapshot.company || "",
        description: snapshot.description || "",
        application_url: snapshot.application_url || "",
        application_email: snapshot.application_email || "",
        resume_version_id: application.resume_version_id || "",
    };
}

export function ApplicationPreparationForm({ application, resumeVersions, onUpdated, onClose }) {
    const { t } = useI18n();
    const [baseline] = useState(() => initialForm(application));
    const [form, setForm] = useState(() => initialForm(application));
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const formRef = useRef(null);
    const titleRef = useRef(null);
    const dirty = Object.keys(baseline).some((field) => baseline[field] !== form[field]);

    useEffect(() => {
        formRef.current?.scrollIntoView?.({ block: "start" });
        titleRef.current?.focus({ preventScroll: true });
    }, []);

    const submit = async (event) => {
        event.preventDefault();
        setBusy(true);
        setError("");
        try {
            const updated = await ApplicationService.updatePreparation(application.id, {
                expected_revision: application.revision,
                title: form.title.trim() || null,
                company: form.company.trim() || null,
                description: form.description.trim() || null,
                application_url: form.application_url.trim() || null,
                application_email: form.application_email.trim() || null,
                resume_version_id: form.resume_version_id || null,
            });
            await onUpdated(updated);
            onClose();
        } catch (updateError) {
            setError(updateError.status === 409 ? t("applicationDetail.conflict") : updateError.message);
        } finally {
            setBusy(false);
        }
    };

    return (
        <form ref={formRef} className="application-preparation-form" onSubmit={submit}>
            <header><div><span>{t("preparation.kicker")}</span><h3 ref={titleRef} tabIndex="-1">{t("preparation.title")}</h3></div><button type="button" className="icon-button" onClick={onClose} aria-label={t("preparation.close")}><i className="bi bi-x-lg" /></button></header>
            <p>{t("preparation.copy")}</p>
            {error && <div className="inline-alert inline-alert--danger" role="alert">{error}</div>}
            <div className="form-grid form-grid--2">
                <label className="field-stack"><span>{t("preparation.roleTitle")}</span><input className="form-control" maxLength="240" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
                <label className="field-stack"><span>{t("preparation.company")}</span><input className="form-control" maxLength="240" value={form.company} onChange={(event) => setForm({ ...form, company: event.target.value })} /></label>
            </div>
            <label className="field-stack"><span>{t("preparation.description")}</span><textarea className="form-control" rows="6" maxLength="100000" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
            <div className="form-grid form-grid--2">
                <label className="field-stack"><span>{t("preparation.applicationUrl")}</span><input className="form-control" type="url" maxLength="2048" placeholder="https://…" value={form.application_url} onChange={(event) => setForm({ ...form, application_url: event.target.value })} /></label>
                <label className="field-stack"><span>{t("preparation.applicationEmail")}</span><input className="form-control" type="email" maxLength="320" placeholder={t("preparation.emailPlaceholder")} value={form.application_email} onChange={(event) => setForm({ ...form, application_email: event.target.value })} /></label>
            </div>
            <label className="field-stack"><span>{t("preparation.resumeVersion")}</span><select className="form-select" value={form.resume_version_id} onChange={(event) => setForm({ ...form, resume_version_id: event.target.value })}><option value="">{t("applications.none")}</option>{resumeVersions.map((version) => <option key={version.id} value={version.id}>{version.label}</option>)}</select></label>
            <div className="preparation-resume-help"><span>{resumeVersions.length ? t("preparation.resumeHelp") : t("preparation.noResumes")}</span><Link to="/resumes">{t("preparation.openResumeStudio")} <i className="bi bi-arrow-right" /></Link></div>
            <div className="button-cluster"><button type="button" className="button button--ghost" onClick={onClose}>{t("preparation.cancel")}</button><button className="button button--primary" disabled={busy || !dirty}>{busy ? t("preparation.saving") : t("preparation.save")}</button></div>
        </form>
    );
}
