import React, { memo, useState } from "react";
import { ScoreBadge } from "./Badges";
import { DismissDialog } from "./DismissDialog";

export const MobileJobCard = memo(function MobileJobCard({ job, isGlobalView, onToggleApplied, isAppliedPending = false, onCopy, onViewAnalysis, onDismiss, onReactivate }) {
    const [showDismissDialog, setShowDismissDialog] = useState(false);
    const applyUrl = job.application_url || job.external_url;
    const sourceUrl = job.external_url && job.external_url !== applyUrl ? job.external_url : null;
    const mailtoUrl = job.application_email ? `mailto:${job.application_email}` : null;
    const fmtDistance = job.distance_km != null ? parseFloat(Number(job.distance_km).toFixed(2)) : null;

    const handleDismiss = (signal) => {
        setShowDismissDialog(false);
        if (onDismiss) onDismiss(job, signal);
    };

    return (
        <div className="glass-panel p-3 mb-3 border border-white-5 hover-elevation hover-transform">
            <div className="d-flex justify-content-between align-items-start mb-3">
                <div className="flex-grow-1 min-w-0 me-2">
                    <h6 className="text-white mb-1 fw-bold text-truncate">{job.title}</h6>
                    <div className="d-flex align-items-center gap-2 text-secondary small">
                        <span className="text-truncate fw-medium max-w-120">{job.company}</span>
                        <span className="opacity-25">|</span>
                        <span>{job.location || "Remote"}</span>
                    </div>
                </div>
                <div className="d-flex flex-column align-items-end gap-2">
                    {!isGlobalView && job.affinity_score != null && (
                        <ScoreBadge score={Math.round(job.affinity_score)} />
                    )}
                    {!isGlobalView && job.worth_applying && (
                        <span className="bg-success rounded-circle d-inline-flex align-items-center justify-content-center sz-18" title="Top Pick">
                            <i className="bi bi-check-lg text-white text-07"></i>
                        </span>
                    )}

                    {!isGlobalView && job.affinity_analysis && (
                        <button 
                            className="btn btn-sm btn-icon btn-secondary rounded-circle d-flex align-items-center justify-content-center border-0 bg-white-5 sz-24"
                            onClick={() => onViewAnalysis(job)}
                            title="View Analysis"
                        >
                            <i className="bi bi-robot text-08"></i>
                        </button>
                    )}
                </div>
            </div>

            <div className="x-small text-secondary mb-3 d-flex flex-wrap gap-x-3 gap-y-1 opacity-75">
                <div><i className="bi bi-clock me-1"></i> {new Date(job.created_at).toLocaleDateString()}</div>
                {job.publication_date && <div><i className="bi bi-megaphone me-1"></i> {new Date(job.publication_date).toLocaleDateString()}</div>}
                {fmtDistance != null && <div><i className="bi bi-geo-alt me-1"></i> {fmtDistance}km</div>}
                {job.workload != null && <div className="text-info fw-bold">{job.workload}%</div>}
            </div>

            <div className="d-flex justify-content-between align-items-center pt-3 border-top border-white-10">
                <div className="d-flex gap-2">
                    {applyUrl && (
                        <a href={applyUrl} target="_blank" rel="noopener noreferrer" className="btn btn-sm btn-primary px-3 rounded-md fw-bold">
                            Apply
                        </a>
                    )}
                    <button onClick={() => onCopy(job)} className="btn btn-sm btn-secondary rounded-circle btn-icon" title="Copy Info">
                        <i className="bi bi-clipboard text-08"></i>
                    </button>
                    {mailtoUrl && (
                        <a href={mailtoUrl} className="btn btn-sm btn-secondary rounded-circle btn-icon" title="Email">
                            <i className="bi bi-envelope text-08"></i>
                        </a>
                    )}
                    {sourceUrl && (
                        <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="btn btn-sm btn-secondary rounded-circle btn-icon" title="Source">
                            <i className="bi bi-link-45deg text-1"></i>
                        </a>
                    )}
                    {/* Dismiss / Reactivate button */}
                    {job.dismissed && onReactivate ? (
                        <button
                            className="btn btn-sm btn-secondary rounded-circle btn-icon"
                            title="Reactivate Job"
                            onClick={() => onReactivate(job)}
                        >
                            <i className="bi bi-arrow-counterclockwise text-08"></i>
                        </button>
                    ) : onDismiss && !job.dismissed && (
                        <button
                            className="btn btn-sm btn-secondary rounded-circle btn-icon"
                            title="Not Interested"
                            onClick={() => setShowDismissDialog(true)}
                        >
                            <i className="bi bi-x-circle text-08"></i>
                        </button>
                    )}
                </div>
                
                <div className="d-flex flex-column align-items-end gap-1">
                    <div className="form-check form-switch m-0">
                        <input
                            className="form-check-input ms-0 toggle-sm"
                            type="checkbox"
                            checked={job.applied}
                            disabled={isAppliedPending}
                            onChange={() => onToggleApplied(job)}
                            title={isAppliedPending ? "Updating Applied Status" : "Toggle Applied Status"}
                        />
                    </div>
                    {job.applied_elsewhere && !job.applied && (
                        <span
                            className="d-flex align-items-center gap-1 text-06 text-warn-custom"
                            title="Applied in another search"
                        >
                            <i className="bi bi-check2-circle"></i>
                            elsewhere
                        </span>
                    )}
                </div>
            </div>

            <DismissDialog
                open={showDismissDialog}
                jobTitle={job.title}
                onDismiss={handleDismiss}
                onClose={() => setShowDismissDialog(false)}
            />
        </div>
    );
});
