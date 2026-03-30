import React, { useState, useEffect } from "react";
import { MobileJobCard } from "./JobTable/MobileJobCard";
import { DesktopJobRow } from "./JobTable/DesktopJobRow";
import { JobAnalysisModal } from "./JobTable/JobAnalysisModal";
import { DismissDialog } from "./JobTable/DismissDialog";
import { JobService } from "../services/jobs";
import { useToast } from "../context/ToastContext";

export function JobTable({ jobs, isGlobalView, onToggleApplied, isAppliedPending = () => false, onDismiss, onReactivate, pagination, onPageChange, isLoading = false }) {
    const [selectedJobForAnalysis, setSelectedJobForAnalysis] = useState(null);
    const [selectedJobForDismiss, setSelectedJobForDismiss] = useState(null);
    const { showToast } = useToast();

    const handleViewAnalysis = (job) => {
        setSelectedJobForAnalysis(job);
        // Fire-and-forget view recording (idempotent on the server)
        if (job?.id) {
            JobService.recordView(job.id).catch((error) => {
                console.warn(`Failed to record job view for ${job.id}`, error);
            });
        }
    };

    useEffect(() => {
        if (!selectedJobForAnalysis) return;
        const handleEscape = (e) => {
            if (e.key === "Escape") setSelectedJobForAnalysis(null);
        };
        document.addEventListener("keydown", handleEscape);
        return () => document.removeEventListener("keydown", handleEscape);
    }, [selectedJobForAnalysis]);

    const handleOpenDismissDialog = (job) => {
        setSelectedJobForDismiss(job);
    };

    const handleDismissFromDialog = (signal) => {
        if (selectedJobForDismiss && onDismiss) {
            onDismiss(selectedJobForDismiss, signal);
        }
        setSelectedJobForDismiss(null);
    };

    const handleCopy = (job) => {
        const data = {
            // Core
            title: job.title,
            company: job.company,
            description: job.description,
            location: job.location,
            platform: job.platform,
            platform_job_id: job.platform_job_id,
            // URLs
            external_url: job.external_url,
            application_url: job.application_url,
            application_email: job.application_email,
            // Dates
            created_at: job.created_at,
            publication_date: job.publication_date,
            // Work details
            workload: job.workload,
            distance_km: job.distance_km,
            // Scores
            affinity_score: job.affinity_score,
            worth_applying: job.worth_applying,
            skill_match_score: job.skill_match_score,
            experience_match_score: job.experience_match_score,
            intent_match_score: job.intent_match_score,
            language_match_score: job.language_match_score,
            location_match_score: job.location_match_score,
            transferability_score: job.transferability_score,
            qualification_gap_score: job.qualification_gap_score,
            // Analysis
            affinity_analysis: job.affinity_analysis,
            analysis_structured: job.analysis_structured,
            red_flags: job.red_flags,
            // Metadata
            raw_metadata: job.raw_metadata,
            normalized_job: job.normalized_job,
            // User state
            applied: job.applied,
            dismissed: job.dismissed,
            feedback_signal: job.feedback_signal,
        };
        // Remove null/undefined keys for cleaner output
        const cleaned = Object.fromEntries(Object.entries(data).filter(([, v]) => v != null));
        navigator.clipboard.writeText(JSON.stringify(cleaned, null, 2)).then(
            () => showToast("Copied to clipboard", "success"),
            () => showToast("Failed to copy to clipboard")
        );
    };
    if (!jobs || jobs.length === 0) {
        if (isLoading) {
            return (
                <div className="text-center py-5 d-flex flex-column align-items-center justify-content-center min-h-240">
                    <div className="spinner-border text-primary mb-3" style={{ width: '2.5rem', height: '2.5rem' }} role="status">
                        <span className="visually-hidden">Loading jobs...</span>
                    </div>
                    <p className="text-secondary mb-0">Loading jobs...</p>
                </div>
            );
        }
        return (
            <div className="text-center py-5 animate-fade-in align-items-center d-flex flex-column justify-content-center min-h-240">
                <div className="mb-4">
                    <div className="rounded-circle bg-secondary bg-opacity-10 d-inline-flex align-items-center justify-content-center sz-80">
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
                        onViewAnalysis={handleViewAnalysis}
                        onOpenDismissDialog={onDismiss ? handleOpenDismissDialog : undefined}
                        onReactivate={onReactivate}
                    />
                ))}
            </div>

            {/* Desktop View (Table) */}
            <div className="d-none d-lg-block flex-grow-1 overflow-auto custom-scrollbar">
                <table className="table table-hover align-middle mb-0 table-separate">
                    <thead className="sticky-top bg-dark z-10">
                        <tr>
                            <th className="ps-4 py-3 bg-black-50 text-secondary text-uppercase x-small tracking-wider border-bottom border-white-10 col-w-30">Job Title</th>
                            <th className="py-3 bg-black-50 text-secondary text-uppercase x-small tracking-wider border-bottom border-white-10 col-w-25">Company & Location</th>
                            {!isGlobalView && (
                                <>
                                    <th className="py-3 bg-black-50 text-secondary text-uppercase x-small tracking-wider border-bottom border-white-10 col-w-20">Match & Details</th>
                                </>
                            )}
                            <th className="py-3 bg-black-50 text-secondary text-uppercase x-small tracking-wider border-bottom border-white-10 col-w-8">Applied</th>
                            <th className={`pe-4 py-3 bg-black-50 text-end text-secondary text-uppercase x-small tracking-wider border-bottom border-white-10 ${isGlobalView ? 'col-w-42' : 'col-w-12'}`}>Actions</th>
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
                                onViewAnalysis={handleViewAnalysis}
                                onOpenDismissDialog={onDismiss ? handleOpenDismissDialog : undefined}
                                onReactivate={onReactivate}
                            />
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Analysis Modal */}
            <JobAnalysisModal job={selectedJobForAnalysis} onClose={() => setSelectedJobForAnalysis(null)} />

            {/* Dismiss Dialog (full-screen portal) */}
            <DismissDialog
                open={!!selectedJobForDismiss}
                jobTitle={selectedJobForDismiss?.title}
                onDismiss={handleDismissFromDialog}
                onClose={() => setSelectedJobForDismiss(null)}
            />

            {/* Pagination Footer */}
            <div className="p-3 border-top border-white-10 bg-black-20 rounded-bottom">
                <div className="d-flex justify-content-between align-items-center">
                    <div className="text-secondary x-small fw-medium">
                        Showing <span className="text-white">{(pagination.page - 1) * 20 + 1}-{Math.min(pagination.page * 20, pagination.total)}</span> of <span className="text-white">{pagination.total}</span>
                    </div>

                    {pagination.pages > 1 && (
                        <div className="d-flex align-items-center gap-2">
                            <button
                                className="btn btn-sm btn-secondary btn-icon sz-32"
                                aria-label="Previous page"
                                disabled={pagination.page === 1}
                                onClick={() => onPageChange(pagination.page - 1)}
                            >
                                <i className="bi bi-chevron-left"></i>
                            </button>

                            <span className="text-white small fw-bold px-2">
                                {pagination.page} <span className="text-secondary fw-normal">/ {pagination.pages}</span>
                            </span>

                            <button
                                className="btn btn-sm btn-secondary btn-icon sz-32"
                                aria-label="Next page"
                                disabled={pagination.page === pagination.pages}
                                onClick={() => onPageChange(pagination.page + 1)}
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
