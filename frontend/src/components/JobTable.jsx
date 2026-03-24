import React, { useState } from "react";
import { createPortal } from "react-dom";
import { MobileJobCard } from "./JobTable/MobileJobCard";
import { DesktopJobRow } from "./JobTable/DesktopJobRow";
import { ScoreBadge } from "./JobTable/Badges";

export function JobTable({ jobs, isGlobalView, onToggleApplied, pagination, onPageChange }) {
    const [selectedJobForAnalysis, setSelectedJobForAnalysis] = useState(null);
    const handleCopy = (job) => {
        const text = JSON.stringify({
            title: job.title,
            company: job.company,
            location: job.location,
            description: job.description,
            url: job.external_url || job.application_url
        }, null, 2);
        navigator.clipboard.writeText(text);
    };
    if (!jobs || jobs.length === 0) {
        return (
            <div className="glass-panel text-center py-5 animate-fade-in align-items-center d-flex flex-column justify-content-center h-100">
                <div className="mb-4">
                    <div className="rounded-circle bg-secondary bg-opacity-10 d-inline-flex align-items-center justify-content-center" style={{ width: 80, height: 80 }}>
                        <i className="bi bi-search fs-1 text-secondary opacity-50"></i>
                    </div>
                </div>
                <h4 className="text-white fw-bold">No jobs found</h4>
                <p className="text-secondary max-w-sm">Try adjusting your filters or starting a new search to find opportunities.</p>
            </div>
        );
    }

    return (
        <div className="animate-fade-in h-100 d-flex flex-column">
            {/* Mobile View (Cards) */}
            <div className="d-lg-none">
                {jobs.map(job => (
                    <MobileJobCard 
                        key={job.id} 
                        job={job} 
                        isGlobalView={isGlobalView} 
                        onToggleApplied={onToggleApplied} 
                        onCopy={handleCopy}
                        onViewAnalysis={(j) => setSelectedJobForAnalysis(j)}
                    />
                ))}
            </div>

            {/* Desktop View (Table) */}
            <div className="d-none d-lg-block flex-grow-1 overflow-auto custom-scrollbar">
                <table className="table table-hover align-middle mb-0" style={{ borderCollapse: 'separate', borderSpacing: '0' }}>
                    <thead className="sticky-top bg-dark" style={{ zIndex: 10 }}>
                        <tr>
                            <th className="ps-4 py-3 bg-black-50 text-secondary text-uppercase x-small tracking-wider border-bottom border-white-10" style={{ width: "30%" }}>Job Title</th>
                            <th className="py-3 bg-black-50 text-secondary text-uppercase x-small tracking-wider border-bottom border-white-10" style={{ width: "25%" }}>Company & Location</th>
                            {!isGlobalView && (
                                <>
                                    <th className="py-3 bg-black-50 text-secondary text-uppercase x-small tracking-wider border-bottom border-white-10" style={{ width: "20%" }}>Match & Details</th>
                                </>
                            )}
                            <th className="py-3 bg-black-50 text-secondary text-uppercase x-small tracking-wider border-bottom border-white-10" style={{ width: "8%" }}>Applied</th>
                            <th className="pe-4 py-3 bg-black-50 text-end text-secondary text-uppercase x-small tracking-wider border-bottom border-white-10" style={{ width: isGlobalView ? "42%" : "12%" }}>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {jobs.map((job) => (
                            <DesktopJobRow 
                                key={job.id} 
                                job={job} 
                                isGlobalView={isGlobalView} 
                                onToggleApplied={onToggleApplied} 
                                onCopy={handleCopy} 
                                onViewAnalysis={(j) => setSelectedJobForAnalysis(j)}
                            />
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Top-level Analysis Modal - Centered on screen */}
            {selectedJobForAnalysis && createPortal(
                <div className="position-fixed top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center animate-fade-in" 
                     style={{ zIndex: 9999, backgroundColor: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(8px)' }}>
                    <div className="glass-panel p-4 m-3 animate-slide-up shadow-2xl" 
                         style={{ maxWidth: '700px', width: '95%', maxHeight: '85vh', overflowY: 'auto', border: '1px solid rgba(255,255,255,0.1)' }}>
                        <div className="d-flex justify-content-between align-items-center mb-4 border-bottom border-white-10 pb-3">
                            <div>
                                <h5 className="mb-1 text-white d-flex align-items-center gap-2">
                                    <i className="bi bi-robot text-info"></i>
                                    AI Match Analysis
                                </h5>
                                <div className="x-small text-secondary fw-bold text-uppercase tracking-wider">
                                    {selectedJobForAnalysis.title} <span className="mx-1 text-muted">•</span> {selectedJobForAnalysis.company}
                                </div>
                            </div>
                            <button className="btn btn-link text-secondary p-0 hover-text-white transition-all" onClick={() => setSelectedJobForAnalysis(null)}>
                                <i className="bi bi-x-lg fs-5"></i>
                            </button>
                        </div>
                        <div className="text-secondary section-text" style={{ lineHeight: '1.7', whiteSpace: 'pre-wrap', fontSize: '0.95rem' }}>
                            {selectedJobForAnalysis.affinity_analysis}
                        </div>
                        <div className="mt-5 pt-3 border-top border-white-10 d-flex justify-content-between align-items-center">
                            <ScoreBadge score={Math.round(selectedJobForAnalysis.affinity_score)} />
                            <button className="btn btn-secondary px-5 rounded-pill fw-bold" onClick={() => setSelectedJobForAnalysis(null)}>Close</button>
                        </div>
                    </div>
                </div>, document.body
            )}

            {/* Pagination Footer */}
            <div className="p-3 border-top border-white-10 bg-black-20 rounded-bottom">
                <div className="d-flex justify-content-between align-items-center">
                    <div className="text-secondary x-small fw-medium">
                        Showing <span className="text-white">{(pagination.page - 1) * 20 + 1}-{Math.min(pagination.page * 20, pagination.total)}</span> of <span className="text-white">{pagination.total}</span>
                    </div>

                    {pagination.pages > 1 && (
                        <div className="d-flex align-items-center gap-2">
                            <button
                                className="btn btn-sm btn-secondary btn-icon"
                                disabled={pagination.page === 1}
                                onClick={() => onPageChange(pagination.page - 1)}
                                style={{ width: 32, height: 32 }}
                            >
                                <i className="bi bi-chevron-left"></i>
                            </button>

                            <span className="text-white small fw-bold px-2">
                                {pagination.page} <span className="text-secondary fw-normal">/ {pagination.pages}</span>
                            </span>

                            <button
                                className="btn btn-sm btn-secondary btn-icon"
                                disabled={pagination.page === pagination.pages}
                                onClick={() => onPageChange(pagination.page + 1)}
                                style={{ width: 32, height: 32 }}
                            >
                                <i className="bi bi-chevron-right"></i>
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
