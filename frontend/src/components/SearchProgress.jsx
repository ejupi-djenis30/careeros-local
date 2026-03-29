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
    }, [displayStatus?.active_search_indices, displayStatus?.completed_search_indices, displayStatus?.log?.length]);

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

    const {
        state,
        total_searches,
        current_search_index,
        searches_completed,
        active_search_indices,
        completed_search_indices,
        current_query,
        searches_generated,
        jobs_new,
        jobs_duplicates,
        jobs_skipped,
        jobs_analyzed,
        jobs_analyze_total,
        errors,
        log,
        terminal_reason,
    } = displayStatus;
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
    const errorNoticeByReason = {
        search_execution_failed: "Search failed before any provider returned usable results.",
        pipeline_processing_failed: "Search failed while processing fetched jobs before analysis could complete.",
        job_persistence_failed: "Jobs were analyzed, but saving them failed.",
        pipeline_timeout: "Search exceeded the maximum allowed processing time.",
        server_shutdown: "Search was interrupted because the server shut down.",
    };
    const statusNotice = isDone
        ? doneNoticeByReason[terminal_reason]
        : isError
            ? errorNoticeByReason[terminal_reason]
            : null;
    const showDebugLabel = isDone || isError;
    const debugTerminalReason = terminal_reason || "n/a";
    const debugLabel = `LLM_DEBUG state=${state} terminal_reason=${debugTerminalReason} profile_id=${profileId}`;

    // Progress calculation — analysis may run concurrently during the searching phase.
    // monotonic floor: the bar never moves backward while a search is running.
    const progressFloorRef = useRef(0);
    let progressPct = 0;
    let analyzingText = "ANALYZING TARGETS...";
    // analysisRunning is only true when there are MORE jobs still to analyze than have already
    // been analyzed.  When jobs_analyzed === jobs_analyze_total the first batch just completed
    // but more searches may still be in flight; using a ratio of 1.0 at that point would briefly
    // spike the bar to 90 % and then drop it backward once new batches are queued.
    const analysisRunning = (jobs_analyzed || 0) > 0 &&
        (jobs_analyze_total || 0) > (jobs_analyzed || 0);
    const completedSearchCount = searches_completed || 0;

    if (state === "generating") {
        progressPct = 5;
    } else if (state === "searching" && total_searches > 0) {
        // Searching phase: 5 % → 90 % based on completed queries.
        const searchPct = 5 + Math.round((completedSearchCount / total_searches) * 85);
        // Only blend in analysis progress when a stable (non-unity) ratio is available so the
        // bar does not momentarily hit 90 % just because the first small batch finished.
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

    // Apply monotonic floor: the bar cannot move backward within an active run.
    // Terminal states (done / error) bypass this so "done" always snaps to 100 %.
    if (isDone || isError) {
        progressFloorRef.current = 0; // reset for the next run
    } else {
        progressPct = Math.max(progressPct, progressFloorRef.current);
        progressFloorRef.current = progressPct;
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
                    searches_completed={searches_completed}
                    active_search_indices={active_search_indices}
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

                {statusNotice && (
                    <div className={`alert ${isError ? 'alert-danger' : 'alert-warning'} py-2 px-3 mb-3 small`} role="status">
                        {statusNotice}
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
                        // jobs_new is updated live as jobs are saved during searching —
                        // show it with a contextual label ("Saved" while running, "New Intel" when done).
                        isRunning
                            ? { label: 'Saved', value: jobs_new, color: 'text-primary' }
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
                    active_search_indices={active_search_indices}
                    completed_search_indices={completed_search_indices}
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
