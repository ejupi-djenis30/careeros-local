import React, { useState, useEffect, useRef } from "react";
import { SearchService } from "../services/search";
import { useToast } from "../context/ToastContext";
import { ProgressHeader } from "./SearchProgress/ProgressHeader";
import { ProgressBar } from "./SearchProgress/ProgressBar";
import { TargetQueue } from "./SearchProgress/TargetQueue";
import { LiveLogs } from "./SearchProgress/LiveLogs";

export function SearchProgress({ profileId, status, onStateChange, onClear }) {
    const logEndRef = useRef(null);
    const reportedState = useRef(null);
    const { showToast } = useToast();
    const [cachedStatus, setCachedStatus] = useState(status);

    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        if (status) setCachedStatus(status);
    }, [status]);

    const displayStatus = status || cachedStatus;

    useEffect(() => {
        if (!displayStatus) return;
        const s = displayStatus.state;
        if ((s === "done" || s === "error") && reportedState.current !== s) {
            reportedState.current = s;
            onStateChange?.(s);
        }
    }, [displayStatus, onStateChange]);

    const activeItemRef = useRef(null);
    useEffect(() => {
        if (activeItemRef.current) {
            activeItemRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }, [displayStatus?.current_search_index, displayStatus?.log?.length]);

    const handleStop = async () => {
        try {
            await SearchService.stopSearch(profileId);
        } catch (e) {
            console.error("Stop error:", e);
            showToast("Failed to stop search. Please try again.");
        }
    };

    if (!displayStatus) return (
        <div className="glass-panel p-5 text-center mt-4 d-flex flex-column align-items-center justify-content-center" style={{ minHeight: '400px' }}>
            <div className="spinner-border text-primary mb-4" role="status" style={{ width: '3rem', height: '3rem' }}></div>
            <h5 className="text-white fw-bold">Initializing Uplink</h5>
            <p className="text-secondary mb-0 font-monospace small">Establishing connection to agent...</p>
        </div>
    );

    const { state, total_searches, current_search_index, current_query, searches_generated, jobs_new, jobs_duplicates, jobs_skipped, jobs_analyzed, jobs_analyze_total, errors, log, terminal_reason } = displayStatus;
    const isRunning = state === "generating" || state === "searching" || state === "analyzing";
    const isDone = state === "done";
    const isError = state === "error" || state === "stopped";
    const doneNoticeByReason = {
        no_queries: "Search completed with notice: no valid queries were generated.",
        no_results: "Search completed with notice: no jobs were found for the generated queries.",
        all_duplicates: "Search completed with notice: all found jobs were already present in history.",
        no_relevant_jobs: "Search completed with notice: no jobs passed relevance filtering.",
        no_jobs_after_structured_filters: "Search completed with notice: all fetched jobs were filtered out by structured constraints.",
    };
    const doneNotice = isDone ? doneNoticeByReason[terminal_reason] : null;
    const showDebugLabel = isDone || isError;
    const debugTerminalReason = terminal_reason || "n/a";
    const debugLabel = `LLM_DEBUG state=${state} terminal_reason=${debugTerminalReason} profile_id=${profileId}`;

    // Progress calculation — analysis may run concurrently during the searching phase.
    let progressPct = 0;
    let analyzingText = "ANALYZING TARGETS...";
    const analysisRunning = (jobs_analyzed || 0) > 0 && (jobs_analyze_total || 0) > 0;

    if (state === "generating") {
        progressPct = 5;
    } else if (state === "searching" && total_searches > 0) {
        // Searching phase: 5% → 90% (extended range to accommodate concurrent analysis)
        const searchPct = 5 + Math.round((current_search_index / total_searches) * 85);
        // If analysis is also running, let the higher progress win so the bar never goes backward.
        const analysisPct = analysisRunning
            ? 5 + Math.round((jobs_analyzed / jobs_analyze_total) * 85)
            : 0;
        progressPct = Math.max(searchPct, analysisPct);
        if (analysisRunning) {
            analyzingText = `ANALYZING TARGETS (${jobs_analyzed}/${jobs_analyze_total})...`;
        }
    } else if (state === "analyzing") {
        progressPct = 90;
        if (analysisRunning) {
            progressPct = 90 + Math.round((jobs_analyzed / jobs_analyze_total) * 10);
            analyzingText = `ANALYZING TARGETS (${jobs_analyzed}/${jobs_analyze_total})...`;
        }
    } else if (isDone) {
        progressPct = 100;
    }

    const analyzedJobs = [];
    if (state === "analyzing" && log) {
        let currentJob = null;
        log.forEach(entry => {
            const analyzingMatch = entry.message.match(/Analyzing (\d+)\/(\d+)[:\s]*(.*)/);
            if (analyzingMatch) {
                if (currentJob) {
                    currentJob.status = 'done';
                    analyzedJobs.push(currentJob);
                }
                currentJob = {
                    idx: parseInt(analyzingMatch[1], 10),
                    total: parseInt(analyzingMatch[2], 10),
                    title: analyzingMatch[3],
                    status: 'analyzing'
                };
            }
        });
        if (currentJob) analyzedJobs.push(currentJob);
    }

    return (
        <div className="animate-fade-in py-3 h-100 d-flex flex-column">
            {/* Main Status Header */}
            <div className="glass-panel p-4 mb-4 position-relative overflow-hidden">
                {/* Background Ambient Glow Removed */}

                <ProgressHeader 
                    isDone={isDone} 
                    isError={isError} 
                    isRunning={isRunning} 
                    state={state} 
                    current_search_index={current_search_index} 
                    total_searches={total_searches} 
                    handleStop={handleStop} 
                    onClear={onClear} 
                />

                <ProgressBar 
                    state={state} 
                    isDone={isDone} 
                    isError={isError} 
                    isRunning={isRunning} 
                    progressPct={progressPct} 
                    analyzingText={analyzingText} 
                    current_query={current_query} 
                />

                {doneNotice && (
                    <div className="alert alert-warning py-2 px-3 mb-3 small" role="status">
                        {doneNotice}
                    </div>
                )}

                {showDebugLabel && (
                    <div className="mb-3 d-flex justify-content-end">
                        <span
                            className="badge bg-dark border border-warning text-warning small font-monospace"
                            title="Technical debug label for automated diagnosis"
                            data-testid="llm-debug-label"
                        >
                            {debugLabel}
                        </span>
                    </div>
                )}

                {/* Stats Grid */}
                <div className="row g-3">
                    {[
                        // During searching, show live analysis count if available; otherwise show final saved count.
                        state === 'searching' && analysisRunning
                            ? { label: 'Analyzed', value: jobs_analyzed, color: 'text-primary' }
                            : { label: 'New Intel', value: jobs_new, color: 'text-white' },
                        { label: 'Duplicates', value: jobs_duplicates, color: 'text-warning' },
                        { label: 'Skipped', value: jobs_skipped, color: 'text-secondary' },
                        { label: 'Errors', value: errors, color: 'text-danger' }
                    ].map((stat, i) => (
                        <div key={i} className="col-6 col-md-3">
                            <div className="p-3 rounded-4 bg-black-20 border border-white-5 text-center">
                                <div className={`display-6 fw-bold mb-0 ${stat.color}`}>{stat.value || 0}</div>
                                <div className="text-secondary x-small text-uppercase tracking-wide opacity-75">{stat.label}</div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            <div className="row g-4 flex-grow-1" style={{ minHeight: '400px', height: '500px', maxHeight: '50vh' }}>
                <TargetQueue 
                    state={state} 
                    analyzedJobs={analyzedJobs} 
                    searches_generated={searches_generated} 
                    current_search_index={current_search_index} 
                    activeItemRef={activeItemRef}
                    jobs_analyzed={jobs_analyzed}
                    jobs_analyze_total={jobs_analyze_total}
                />

                <LiveLogs 
                    log={log} 
                    logEndRef={logEndRef} 
                />
            </div>
        </div>
    );
}
