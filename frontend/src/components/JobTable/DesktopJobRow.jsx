import React from "react";
import { ScoreBadge } from "./Badges";

export function DesktopJobRow({ job, isGlobalView, onToggleApplied, onCopy, onViewAnalysis }) {
    const applyUrl = job.application_url || job.external_url; // Use application_url falling back to external_url for 'Apply'
    const sourceUrl = job.external_url;   // Use external_url for 'Source'
    const mailtoUrl = job.application_email ? `mailto:${job.application_email}` : null;

    return (
        <tr className="job-row border-bottom border-white-5 hover-elevation" style={{ transition: 'all 0.2s' }}>
            <td className="ps-4 py-4 border-0">
                <div className="fw-bold text-white text-truncate" style={{ maxWidth: 280 }} title={job.title}>
                    {job.title}
                </div>
                <div className="x-small text-secondary mt-1 d-flex gap-2">
                    <span title="Scraped on">
                        <i className="bi bi-clock x-small me-1"></i>
                        {new Date(job.created_at).toLocaleDateString()}
                    </span>
                    {job.publication_date && (
                        <span className="text-info opacity-75" title="Published on">
                            <i className="bi bi-megaphone x-small me-1"></i>
                            {new Date(job.publication_date).toLocaleDateString()}
                        </span>
                    )}
                </div>
            </td>
            <td className="border-0">
                <div className="text-white fw-medium text-truncate" style={{ maxWidth: 200 }} title={job.company}>
                    {job.company}
                </div>
                <div className="text-secondary small d-flex align-items-center gap-2">
                    <i className="bi bi-geo-alt opacity-50"></i>
                    {job.location || "Remote"}
                    {job.distance_km != null && <span className="text-white-50 opacity-75">({job.distance_km}km)</span>}
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
                                <span className="bg-success rounded-circle d-inline-flex align-items-center justify-content-center" 
                                      style={{width: '18px', height: '18px'}} title="Top Pick">
                                    <i className="bi bi-check-lg text-white" style={{fontSize: '0.7rem'}}></i>
                                </span>
                            )}
                            {job.workload && job.workload < 100 && (
                                <span className="badge-pill badge-info border-0 py-1" style={{fontSize: '0.65rem'}}>
                                    {job.workload}%
                                </span>
                            )}
                            {job.affinity_analysis && (
                                <button 
                                    className="btn btn-sm btn-icon btn-secondary rounded-circle d-flex align-items-center justify-content-center border-0 bg-white-5 hover-bg-white-10 ms-1"
                                    onClick={() => onViewAnalysis(job)}
                                    style={{ width: '28px', height: '28px' }}
                                    title="View Analysis"
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
                            className="form-check-input"
                            type="checkbox"
                            checked={job.applied}
                            onChange={() => onToggleApplied(job)}
                            style={{ cursor: 'pointer' }}
                            title="Toggle Applied Status"
                        />
                    </div>
                    {job.applied_elsewhere && !job.applied && (
                        <span
                            className="badge d-flex align-items-center gap-1"
                            style={{ fontSize: '0.6rem', backgroundColor: 'rgba(255,193,7,0.15)', color: '#ffc107', border: '1px solid rgba(255,193,7,0.3)', borderRadius: '4px', padding: '2px 5px' }}
                            title="You applied to this job in another search"
                        >
                            <i className="bi bi-check2-circle"></i>
                            Elsewhere
                        </span>
                    )}
                </div>
            </td>
            <td className="pe-4 text-end border-0">
                <div className="d-flex justify-content-end gap-2 text-nowrap align-items-center">
                    {mailtoUrl && (
                        <a href={mailtoUrl} className="btn btn-sm btn-icon btn-outline-info border-white-10" title={`Email: ${job.application_email}`}>
                            <i className="bi bi-envelope"></i>
                        </a>
                    )}
                    {applyUrl && (
                        <a href={applyUrl} target="_blank" rel="noopener noreferrer" className="btn btn-sm btn-primary px-3 rounded-md shadow-sm">
                            Apply
                        </a>
                    )}
                    <button onClick={() => onCopy(job)} className="btn btn-sm btn-secondary btn-icon" title="Copy Details">
                        <i className="bi bi-clipboard"></i>
                    </button>
                    {sourceUrl && (
                        <a href={sourceUrl} target="_blank" rel="noopener noreferrer"
                            className="btn btn-sm btn-icon btn-secondary"
                            title={`View on ${job.platform || 'Source'}`}>
                            <i className="bi bi-link-45deg fs-5"></i>
                        </a>
                    )}
                </div>
            </td>
        </tr>
    );
}
