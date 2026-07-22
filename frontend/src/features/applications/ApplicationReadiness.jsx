import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { saveBlob } from "../../lib/download";
import { ApplicationService } from "../../services/applications";
import { useI18n } from "../../i18n/useI18n";

function displayEvidence(value, t) {
    if (value === "True") return t("readiness.value.yes");
    if (value === "False") return t("readiness.value.no");
    if (value === "none") return t("readiness.value.none");
    return value;
}

const EDIT_ACTIONS = new Set(["capture_role_identity", "capture_role_description", "capture_application_route", "link_published_resume"]);
const ACTION_DESTINATIONS = {
    complete_career_profile: "/profile",
    strengthen_career_profile: "/profile",
    export_resume_files: "/resumes",
    republish_resume_artifacts: "/resumes",
    republish_valid_resume: "/resumes",
    refresh_resume: "/resumes",
    verify_resume_facts: "/resumes",
};

function ReadinessCheck({ check, onEditPreparation }) {
    const { t } = useI18n();
    const icon = check.status === "pass" ? "bi-check-lg" : check.status === "warning" ? "bi-exclamation-lg" : "bi-x-lg";
    const destination = ACTION_DESTINATIONS[check.action];
    return (
        <article className={`readiness-check readiness-check--${check.status}`}>
            <div className="readiness-check__state"><i className={`bi ${icon}`} aria-hidden="true" /><span>{t(`readiness.status.${check.status}`)}</span></div>
            <div className="readiness-check__body">
                <header><strong>{t(`readiness.check.${check.id}`)}</strong><span>{check.points_awarded}/{check.points_available}</span></header>
                <dl>{check.evidence.map((item) => <div key={item.key}><dt>{t(`readiness.evidence.${item.key}`)}</dt><dd>{displayEvidence(item.value, t)}</dd></div>)}</dl>
                <div className="readiness-check__action"><span><i className="bi bi-arrow-return-right" aria-hidden="true" /> {check.action ? t(`readiness.action.${check.action}`) : t("readiness.noAction")}</span>{EDIT_ACTIONS.has(check.action) && <button type="button" onClick={onEditPreparation}>{t("readiness.editPack")} <i className="bi bi-arrow-right" /></button>}{destination && <Link to={destination}>{destination === "/profile" ? t("readiness.openVault") : t("readiness.openResumeStudio")} <i className="bi bi-arrow-right" /></Link>}</div>
            </div>
        </article>
    );
}

export function ApplicationReadiness({ applicationId, applicationRevision, onEditPreparation = () => {} }) {
    const { t } = useI18n();
    const [result, setResult] = useState({ key: "", report: null, error: "" });
    const [downloadError, setDownloadError] = useState("");
    const [downloading, setDownloading] = useState("");
    const [reload, setReload] = useState(0);
    const requestKey = `${applicationId}:${applicationRevision}:${reload}`;
    const isCurrent = result.key === requestKey;
    const report = isCurrent ? result.report : null;
    const error = downloadError || (isCurrent ? result.error : "");
    const loading = !isCurrent;

    useEffect(() => {
        const controller = new AbortController();
        ApplicationService.readiness(applicationId, { signal: controller.signal })
            .then((next) => { if (!controller.signal.aborted) setResult({ key: requestKey, report: next, error: "" }); })
            .catch((loadError) => { if (!controller.signal.aborted && loadError?.name !== "AbortError") setResult({ key: requestKey, report: null, error: loadError.message }); });
        return () => controller.abort();
    }, [applicationId, requestKey]);

    const download = async (format) => {
        setDownloading(format);
        setDownloadError("");
        try {
            saveBlob(await ApplicationService.downloadReadiness(applicationId, format));
        } catch (downloadError) {
            setDownloadError(downloadError.message);
        } finally {
            setDownloading("");
        }
    };

    return (
        <section className="application-readiness" aria-labelledby="readiness-title">
            <header><div><span>{t("readiness.kicker")}</span><h3 id="readiness-title">{t("readiness.title")}</h3></div>{report && <span className={`readiness-badge readiness-badge--${report.status}`}>{t(`readiness.reportStatus.${report.status}`)}</span>}</header>
            <p className="readiness-disclaimer">{t("readiness.disclaimer")}</p>
            {loading && <div className="readiness-loading" role="status"><span className="spinner-border spinner-border-sm" /><span>{t("readiness.loading")}</span></div>}
            {error && <div className="inline-alert inline-alert--danger" role="alert"><span>{error}</span><button type="button" className="button button--ghost" onClick={() => { setDownloadError(""); setReload((value) => value + 1); }}>{t("readiness.retry")}</button></div>}
            {!loading && report && <>
                <div className="readiness-summary">
                    <div className="readiness-score" role="progressbar" aria-label={t("readiness.scoreLabel")} aria-valuemin="0" aria-valuemax="100" aria-valuenow={report.completeness_score} style={{ "--readiness-score": `${report.completeness_score * 3.6}deg` }}><strong>{report.completeness_score}</strong><span>/100</span></div>
                    <div><strong>{t("readiness.summary", { blockers: report.blocker_count, warnings: report.warning_count })}</strong><small>{t("readiness.localOnly")}</small><code title={report.fingerprint}>{report.fingerprint.slice(0, 12)}</code></div>
                </div>
                <nav className="readiness-tools" aria-label={t("readiness.toolsLabel")}><Link to="/profile"><i className="bi bi-person-vcard" /> {t("readiness.openVault")}</Link><Link to="/resumes"><i className="bi bi-file-earmark-text" /> {t("readiness.openResumeStudio")}</Link></nav>
                <div className="readiness-checks">{report.checks.map((check) => <ReadinessCheck key={check.id} check={check} onEditPreparation={onEditPreparation} />)}</div>
                <div className="readiness-exports"><div><strong>{t("readiness.exportTitle")}</strong><span>{t("readiness.exportCopy")}</span></div><div className="button-cluster"><button type="button" className="button button--secondary" disabled={Boolean(downloading)} onClick={() => download("json")}><i className="bi bi-filetype-json" /> {downloading === "json" ? t("readiness.exporting") : "JSON"}</button><button type="button" className="button button--secondary" disabled={Boolean(downloading)} onClick={() => download("markdown")}><i className="bi bi-markdown" /> {downloading === "markdown" ? t("readiness.exporting") : "Markdown"}</button></div></div>
            </>}
        </section>
    );
}
