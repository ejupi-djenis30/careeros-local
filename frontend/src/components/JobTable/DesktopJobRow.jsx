import React, { memo } from "react";
import { ScoreBadge } from "./Badges";
import { safeExternalUrl, safeMailto } from "../../lib/safeUrl";
import { InternalLink } from "../InternalLink";
import { useI18n } from "../../i18n/useI18n";

export const DesktopJobRow = memo(function DesktopJobRow({ job, isGlobalView, onToggleApplied, isAppliedPending = false, onCopy, onViewAnalysis, onOpenDismissDialog, onReactivate }) {
    const { language, t } = useI18n();
    const locale = language === "it" ? "it-IT" : "en-GB";
    const applyUrl = safeExternalUrl(job.application_url) || safeExternalUrl(job.external_url);
    const externalUrl = safeExternalUrl(job.external_url);
    const sourceUrl = externalUrl && externalUrl !== applyUrl ? externalUrl : null;
    const mailtoUrl = safeMailto(job.application_email);
    const fmtDistance = job.distance_km != null ? parseFloat(Number(job.distance_km).toFixed(2)) : null;

    return (
        <tr className="job-row border-bottom border-white-5 hover-elevation hover-all-200">
            <td className="ps-4 py-4 border-0">
                <div className="fw-bold text-white text-truncate max-w-280" title={job.title}>
                    {job.title}
                </div>
                <div className="x-small text-secondary mt-1 d-flex gap-2">
                    <span title={t("jobs.collectedOn")}>
                        <i className="bi bi-clock x-small me-1"></i>
                        {new Date(job.created_at).toLocaleDateString(locale)}
                    </span>
                    {job.publication_date && (
                        <span className="text-info opacity-75" title={t("jobs.publishedOn")}>
                            <i className="bi bi-megaphone x-small me-1"></i>
                            {new Date(job.publication_date).toLocaleDateString(locale)}
                        </span>
                    )}
                </div>
            </td>
            <td className="border-0">
                <div className="text-white fw-medium text-truncate max-w-200" title={job.company}>
                    {job.company}
                </div>
                <div className="text-secondary small d-flex align-items-center gap-2">
                    <i className="bi bi-geo-alt opacity-50"></i>
                    {job.location || t("jobs.remote")}
                    {fmtDistance != null && <span className="text-white-50 opacity-75">({fmtDistance.toLocaleString(locale)} km)</span>}
                </div>
            </td>
            {!isGlobalView && (
                <td className="border-0">
                    <div className="d-flex align-items-center gap-3">
                        {job.affinity_score != null ? (
                            <ScoreBadge score={Math.round(job.affinity_score)} />
                        ) : <span className="text-muted opacity-25">—</span>}

                        <div className="d-flex flex-wrap gap-1 align-items-center">
                            {job.worth_applying && (
                                <span className="bg-success rounded-circle d-inline-flex align-items-center justify-content-center sz-18" title={t("jobs.topPick")}>
                                    <i className="bi bi-check-lg text-white text-07"></i>
                                </span>
                            )}
                            {job.workload && job.workload < 100 && (
                                <span className="badge-pill badge-info border-0 py-1 text-065">
                                    {job.workload}%
                                </span>
                            )}
                            {job.affinity_analysis && (
                                <button
                                    className="btn btn-sm btn-icon btn-secondary rounded-circle d-flex align-items-center justify-content-center border-0 bg-white-5 hover-bg-white-10 ms-1 sz-28"
                                        onClick={() => onViewAnalysis(job)}
                                    title={t("jobs.viewAnalysis")}
                                >
                                    <i className="bi bi-robot"></i>
                                </button>
                            )}
                        </div>
                    </div>
                </td>
            )}

            <td className="border-0">
                <div className="d-flex flex-column gap-1 align-items-start">
                    <div className="form-check form-switch ms-1 mb-0">
                        <input
                            className="form-check-input cursor-pointer"
                            type="checkbox"
                            checked={job.applied}
                            disabled={isAppliedPending}
                            onChange={() => onToggleApplied(job)}
                            title={isAppliedPending ? t("jobs.updatingApplied") : t("jobs.toggleApplied")}
                        />
                    </div>
                    {job.applied_elsewhere && !job.applied && (
                        <span
                            className="badge d-flex align-items-center gap-1 badge-applied-other"
                            title={t("jobs.appliedElsewhereTitle")}
                        >
                            <i className="bi bi-check2-circle"></i>
                            {t("jobs.elsewhere")}
                        </span>
                    )}
                </div>
            </td>
            <td className="pe-4 text-end border-0">
                <div className="d-flex justify-content-end gap-2 text-nowrap align-items-center">
                    {mailtoUrl && (
                        <a href={mailtoUrl} className="btn btn-sm btn-icon btn-outline-info border-white-10" title={t("jobs.emailTo", { email: job.application_email })}>
                            <i className="bi bi-envelope"></i>
                        </a>
                    )}
                    {applyUrl && (
                        <a href={applyUrl} target="_blank" rel="noopener noreferrer" className="btn btn-sm btn-primary px-3 rounded-2 shadow-sm">
                            {t("jobs.apply")}
                        </a>
                    )}
                    <InternalLink to={`/applications?jobId=${encodeURIComponent(job.id)}`} className="btn btn-sm btn-secondary btn-icon" title={t("jobs.addApplication")}>
                        <i className="bi bi-kanban"></i>
                    </InternalLink>
                    <button onClick={() => onCopy(job)} className="btn btn-sm btn-secondary btn-icon" title={t("jobs.copyDetails")}>
                        <i className="bi bi-clipboard"></i>
                    </button>
                    {sourceUrl && (
                        <a href={sourceUrl} target="_blank" rel="noopener noreferrer"
                            className="btn btn-sm btn-icon btn-secondary"
                            title={t("jobs.viewOnSource", { source: job.platform || t("jobs.source") })}>
                            <i className="bi bi-link-45deg fs-5"></i>
                        </a>
                    )}
                    {/* Dismiss / Reactivate button */}
                    {job.dismissed && onReactivate ? (
                        <button
                            className="btn btn-sm btn-icon btn-secondary rounded-circle"
                            title={t("jobs.reactivate")}
                            onClick={() => onReactivate(job)}
                        >
                            <i className="bi bi-arrow-counterclockwise"></i>
                        </button>
                    ) : onOpenDismissDialog && !job.dismissed && (
                        <button
                            className="btn btn-sm btn-icon btn-secondary rounded-circle"
                            title={t("jobs.notInterested")}
                            onClick={() => onOpenDismissDialog(job)}
                        >
                            <i className="bi bi-x-circle"></i>
                        </button>
                    )}
                </div>
            </td>
        </tr>
    );
});
