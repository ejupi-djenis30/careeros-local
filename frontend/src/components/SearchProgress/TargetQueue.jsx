import React from "react";

export function TargetQueue({ state, analyzedJobs, searches_generated, current_search_index, activeItemRef, jobs_analyzed, jobs_analyze_total }) {
    // During searching, show analysis count badge if analysis is already running concurrently.
    const showAnalysisBadge = state === "searching" && (jobs_analyzed || 0) > 0;
    return (
        <div className="col-lg-5 d-flex flex-column h-100">
            <div className="glass-panel p-0 h-100 overflow-hidden d-flex flex-column">
                <div className="p-3 border-bottom border-white-10 bg-white-5 d-flex align-items-center justify-content-between">
                    <h6 className="mb-0 fw-bold text-white small text-uppercase tracking-wide">
                        <i className={`bi ${state === "analyzing" ? "bi-search" : "bi-diagram-3"} me-2 text-primary`}></i>
                        {state === "analyzing" ? "Analysis Queue" : "Tactical Plan"}
                    </h6>
                    {showAnalysisBadge && (
                        <span className="badge bg-primary-10 text-primary border border-primary-20 rounded-pill font-monospace x-small">
                            {jobs_analyzed}/{jobs_analyze_total || '?'} analyzed
                        </span>
                    )}
                </div>
                <div className="flex-grow-1 overflow-y-auto custom-scrollbar p-0">
                    <ul className="list-group list-group-flush mb-0">
                        {state === "analyzing" ? (
                            analyzedJobs.map((j, i) => {
                                const isCurrent = j.status === 'analyzing';
                                return (
                                    <li key={i} ref={isCurrent ? activeItemRef : null} className={`list-group-item bg-transparent border-bottom border-white-5 px-3 py-3 d-flex gap-3 ${isCurrent ? 'bg-primary-10' : ''}`}>
                                        <div className="mt-1">
                                            {j.status === 'done' ? (
                                                <i className="bi bi-check-circle-fill text-success"></i>
                                            ) : (
                                                <div className="spinner-border spinner-border-sm text-primary"></div>
                                            )}
                                        </div>
                                        <div>
                                            <div className="x-small text-uppercase tracking-wider opacity-50 mb-1 text-secondary">Target {j.idx}/{j.total}</div>
                                            <div className={`small fw-medium font-monospace ${isCurrent ? 'text-primary' : 'text-secondary'}`}>{j.title}</div>
                                        </div>
                                    </li>
                                );
                            })
                        ) : (
                            searches_generated?.map((s, i) => {
                                const currentIndex = (current_search_index || 1) - 1;
                                const isDone = i < currentIndex;
                                const isCurrent = i === currentIndex;

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
                                <span className="small">Formulating strategy...</span>
                            </div>
                        )}
                    </ul>
                </div>
            </div>
        </div>
    );
}
