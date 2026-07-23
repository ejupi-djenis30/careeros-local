import React from "react";
import { useI18n } from "../../i18n/useI18n";

export function TargetQueue({ state, analyzedJobs, searches_generated, active_search_indices, completed_search_indices, activeItemRef, jobs_analyzed, jobs_analyze_total }) {
    const { language, t } = useI18n();
    const locale = language === "it" ? "it-IT" : "en-GB";
    const formatCount = (value) => Number(value || 0).toLocaleString(locale);
    // During searching, show analysis count badge if analysis is already running concurrently.
    const showAnalysisBadge = state === "searching" && (jobs_analyzed || 0) > 0;
    const activeIndices = new Set(active_search_indices || []);
    const completedIndices = new Set(completed_search_indices || []);
    const highestActiveIndex = (active_search_indices || []).length > 0
        ? Math.max(...active_search_indices)
        : null;
    return (
        <div className="col-lg-5 d-flex flex-column h-100">
            <div className="glass-panel p-0 h-100 overflow-hidden d-flex flex-column">
                <div className="p-3 border-bottom border-white-10 bg-white-5 d-flex align-items-center justify-content-between">
                    <h6 className="mb-0 fw-bold text-white small text-uppercase tracking-wide">
                        <i className={`bi ${state === "analyzing" ? "bi-search" : "bi-diagram-3"} me-2 text-primary`}></i>
                        {state === "analyzing" ? t("searchProgress.analysisQueue") : t("searchProgress.plan")}
                    </h6>
                    {showAnalysisBadge && (
                        <span className="badge bg-primary-10 text-primary border border-primary-20 rounded-pill font-monospace x-small">
                            {t("searchProgress.analyzedCount", { current: formatCount(jobs_analyzed), total: jobs_analyze_total ? formatCount(jobs_analyze_total) : "?" })}
                        </span>
                    )}
                </div>
                <div className="flex-grow-1 overflow-y-auto custom-scrollbar p-0">
                    <ul className="list-group list-group-flush mb-0">
                        {state === "analyzing" ? (
                            analyzedJobs.map((j, i) => {
                                const isCurrent = j.status === 'analyzing';
                                const isDone = j.status === 'done';
                                return (
                                    <li key={i} ref={isCurrent ? activeItemRef : null} className={`list-group-item bg-transparent border-bottom border-white-5 px-3 py-3 d-flex gap-3 ${isCurrent ? 'bg-primary-10' : ''}`}>
                                        <div className="mt-1">
                                            {isDone ? (
                                                <i className="bi bi-check-circle-fill text-success"></i>
                                            ) : isCurrent ? (
                                                <div className="spinner-border spinner-border-sm text-primary"></div>
                                            ) : (
                                                <div className="rounded-circle bg-white-10 border border-white-10" style={{ width: 16, height: 16 }}></div>
                                            )}
                                        </div>
                                        <div>
                                            <div className="x-small text-uppercase tracking-wider opacity-50 mb-1 text-secondary">{t("searchProgress.targetOf", { current: formatCount(j.idx), total: formatCount(j.total) })}</div>
                                            <div className={`small fw-medium font-monospace ${isCurrent ? 'text-primary' : 'text-secondary'}`}>{j.title}</div>
                                        </div>
                                    </li>
                                );
                            })
                        ) : (
                            searches_generated?.map((s, i) => {
                                const searchIndex = i + 1;
                                const isDone = completedIndices.has(searchIndex);
                                const isCurrent = activeIndices.has(searchIndex);

                                return (
                                    <li key={i} ref={isCurrent && searchIndex === highestActiveIndex ? activeItemRef : null} className={`list-group-item bg-transparent border-bottom border-white-5 px-3 py-3 d-flex gap-3 ${isCurrent ? 'bg-primary-10' : ''}`}>
                                        <div className="mt-1">
                                            {isDone ? (
                                                <i className="bi bi-check-circle-fill text-success"></i>
                                            ) : isCurrent ? (
                                                <div className="spinner-border spinner-border-sm text-primary"></div>
                                            ) : (
                                                <div className="rounded-circle bg-white-10 border border-white-10" style={{ width: 16, height: 16 }}></div>
                                            )}
                                        </div>
                                        <div>
                                            <div className="x-small text-uppercase tracking-wider opacity-50 mb-1 text-secondary">{s.type || s.provider}</div>
                                            <div className={`small fw-medium font-monospace ${isCurrent ? 'text-primary' : 'text-secondary'}`}>{s.query}</div>
                                        </div>
                                    </li>
                                );
                            })
                        )}
                        {(!searches_generated || searches_generated.length === 0) && state === "generating" && (
                            <div className="p-5 text-center text-secondary opacity-50 d-flex flex-column align-items-center">
                                <div className="spinner-grow spinner-grow-sm mb-3"></div>
                                <span className="small">{t("searchProgress.formulating")}</span>
                            </div>
                        )}
                    </ul>
                </div>
            </div>
        </div>
    );
}
