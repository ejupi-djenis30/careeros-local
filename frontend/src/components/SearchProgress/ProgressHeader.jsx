import React from "react";

export function ProgressHeader({ 
    isDone, 
    isError, 
    isRunning, 
    state, 
    searches_completed,
    active_search_indices,
    total_searches, 
    handleStop, 
    onClear 
}) {
    const completedCount = searches_completed || 0;
    const activeCount = (active_search_indices || []).length;
    const searchSubtitle = activeCount > 0
        ? `Executing ${activeCount} vector${activeCount === 1 ? "" : "s"}; ${completedCount} / ${total_searches} completed...`
        : `Processed ${completedCount} / ${total_searches} vectors...`;

    return (
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-4 mb-4">
            <div className="d-flex align-items-center gap-4">
                <div className={`rounded-circle d-flex align-items-center justify-content-center text-white shadow-lg border border-white-10 ${isDone ? 'bg-success' : isError ? 'bg-danger' : 'bg-primary'}`} style={{ width: 64, height: 64 }}>
                    {isRunning ? <span className="spinner-border spinner-border-sm" style={{ width: '2rem', height: '2rem' }}></span>
                        : isDone ? <i className="bi bi-check-lg fs-2"></i>
                            : <i className="bi bi-exclamation-triangle fs-2"></i>}
                </div>
                <div>
                    <h2 className="mb-0 fw-bold text-white tracking-tight">
                        {isDone ? "Mission Complete" : isError ? (state === "stopped" ? "Mission Aborted" : "Mission Failed") : "Agent Active"}
                    </h2>
                    <p className="text-white-50 mb-0 font-monospace small">
                        {state === "generating" && "Generating tactical search vector..."}
                        {state === "searching" && searchSubtitle}
                        {state === "analyzing" && "Analyzing intelligence data..."}
                        {state === "done" && "All objectives secured."}
                    </p>
                </div>
            </div>

            <div className="d-flex gap-3">
                {isRunning && (
                    <button className="btn btn-outline-danger border-white-10 bg-black-20 rounded-pill px-4 hover-bg-danger hover-text-white transition-all" onClick={handleStop}>
                        <i className="bi bi-stop-circle me-2"></i>Abort
                    </button>
                )}
                {(isDone || isError) && (
                    <button className="btn btn-secondary rounded-pill px-5 shadow-glow" onClick={onClear}>
                        Close
                    </button>
                )}
            </div>
        </div>
    );
}
