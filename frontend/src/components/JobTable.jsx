import React, { useState, useEffect } from "react";
import { MobileJobCard } from "./JobTable/MobileJobCard";
import { DesktopJobRow } from "./JobTable/DesktopJobRow";
import { JobAnalysisModal } from "./JobTable/JobAnalysisModal";

export function JobTable({ jobs, isGlobalView, onToggleApplied, isAppliedPending = () => false, pagination, onPageChange, isLoading = false }) {
    const [selectedJobForAnalysis, setSelectedJobForAnalysis] = useState(null);

    useEffect(() => {
        if (!selectedJobForAnalysis) return;
        const handleEscape = (e) => {
            if (e.key === "Escape") setSelectedJobForAnalysis(null);
        };
        document.addEventListener("keydown", handleEscape);
        return () => document.removeEventListener("keydown", handleEscape);
    }, [selectedJobForAnalysis]);

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
        if (isLoading) {
            return (
                <div className="text-center py-5 d-flex flex-column align-items-center justify-content-center" style={{ minHeight: 240 }}>
                    <div className="spinner-border text-primary mb-3" style={{ width: '2.5rem', height: '2.5rem' }} role="status">
                        <span className="visually-hidden">Loading jobs...</span>
                    </div>
                    <p className="text-secondary mb-0">Loading jobs...</p>
                </div>
            );
        }
        return (
            <div className="text-center py-5 animate-fade-in align-items-center d-flex flex-column justify-content-center" style={{ minHeight: 240 }}>
                <div className="mb-4">
                    <div className="rounded-circle bg-secondary bg-opacity-10 d-inline-flex align-items-center justify-content-center" style={{ width: 80, height: 80 }}>
                        <i className="bi bi-search fs-1 text-secondary opacity-50"></i>
                    </div>
                </div>
                <h4 className="text-white fw-bold">No jobs found</h4>
                <p className="text-secondary">Try adjusting your filters or starting a new search to find opportunities.</p>
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
                        isAppliedPending={isAppliedPending(job.id)}
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
                                isAppliedPending={isAppliedPending(job.id)}
                                onCopy={handleCopy} 
                                onViewAnalysis={(j) => setSelectedJobForAnalysis(j)}
                            />
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Analysis Modal */}
            <JobAnalysisModal job={selectedJobForAnalysis} onClose={() => setSelectedJobForAnalysis(null)} />

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
