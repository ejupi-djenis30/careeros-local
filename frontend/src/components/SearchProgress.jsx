import React, { useEffect, useRef } from "react";
import { SearchService } from "../services/search";
import { useToast } from "../context/ToastContext";
import { ProgressHeader } from "./SearchProgress/ProgressHeader";
import { ProgressBar } from "./SearchProgress/ProgressBar";
import { TargetQueue } from "./SearchProgress/TargetQueue";
import { LiveLogs } from "./SearchProgress/LiveLogs";
import { useI18n } from "../i18n/useI18n";

export function SearchProgress({ profileId, status, onStateChange, onClear }) {
    const logEndRef = useRef(null);
    const reportedState = useRef(null);
    const { showToast } = useToast();
    const { t } = useI18n();
    const displayStatus = status;

    useEffect(() => {
        if (!displayStatus) return;
        const s = displayStatus.state;
        if (["done", "error", "stopped"].includes(s) && reportedState.current !== s) {
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

    // Progress calculation — resolved here (before the early return) so all hooks are
    // unconditional. Optional chaining handles the null displayStatus case.
    const _state = displayStatus?.state;
    const _totalSearches = displayStatus?.total_searches || 0;
    const _searchesCompleted = displayStatus?.searches_completed || 0;
    const _jobsAnalyzed = displayStatus?.jobs_analyzed || 0;
    const _jobsAnalyzeTotal = displayStatus?.jobs_analyze_total || 0;
    const _isDone = _state === "done";
    const _isError = _state === "error" || _state === "stopped";
    const _analysisRunning = _jobsAnalyzed > 0 && _jobsAnalyzeTotal > _jobsAnalyzed;

    let _rawProgressPct = 0;
    let analyzingText = t("searchProgress.analyzingTargets");
    if (_state === "running") {
        _rawProgressPct = 2;
    } else if (_state === "generating") {
        _rawProgressPct = 5;
    } else if (_state === "searching" && _totalSearches > 0) {
        const searchPct = 5 + Math.round((_searchesCompleted / _totalSearches) * 85);
        const analysisPct = _analysisRunning
            ? 5 + Math.round((_jobsAnalyzed / _jobsAnalyzeTotal) * 85)
            : 0;
        _rawProgressPct = Math.max(searchPct, analysisPct);
        if (_analysisRunning) {
            analyzingText = t("searchProgress.analyzingTargetsCount", { current: _jobsAnalyzed, total: _jobsAnalyzeTotal });
        }
    } else if (_state === "analyzing") {
        _rawProgressPct = 90;
        if (_analysisRunning) {
            _rawProgressPct = 90 + Math.round((_jobsAnalyzed / _jobsAnalyzeTotal) * 10);
            analyzingText = t("searchProgress.analyzingTargetsCount", { current: _jobsAnalyzed, total: _jobsAnalyzeTotal });
        }
    } else if (_isDone) {
        _rawProgressPct = 100;
    }

    const handleStop = async () => {
        try {
            await SearchService.stopSearch(profileId);
        } catch (e) {
            console.error("Stop error:", e);
            showToast(t("searchProgress.stopFailed"));
        }
    };

    if (!displayStatus) return (
        <div className="glass-panel p-5 text-center mt-4 d-flex flex-column align-items-center justify-content-center" style={{ minHeight: '400px' }}>
            <div className="spinner-border text-primary mb-4" role="status" style={{ width: '3rem', height: '3rem' }}></div>
            <h5 className="text-white fw-bold">{t("searchProgress.initializing")}</h5>
            <p className="text-secondary mb-0 font-monospace small">{t("searchProgress.connecting")}</p>
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
        jobs_unique,
        jobs_duplicates,
        jobs_duplicates_total,
        jobs_duplicates_runtime,
        jobs_duplicates_history,
        jobs_duplicates_catalog_conflicts,
        jobs_skipped,
        jobs_analyzed,
        jobs_analyze_total,
        analysis_targets,
        analysis_current_index,
        errors,
        log,
        terminal_reason,
    } = displayStatus;
    const isRunning = ["running", "generating", "searching", "analyzing"].includes(state);
    const isDone = state === "done";
    const isError = state === "error" || state === "stopped";
    const doneNoticeByReason = {
        no_queries: t("searchProgress.notice.noQueries"),
        no_valid_queries_after_filter: t("searchProgress.notice.noValidQueries"),
        no_queries_matching_preferences: t("searchProgress.notice.noMatchingQueries"),
        no_results: t("searchProgress.notice.noResults"),
        all_duplicates: t("searchProgress.notice.allDuplicates"),
        no_jobs_after_dedup: t("searchProgress.notice.afterDedup"),
        no_relevant_jobs: t("searchProgress.notice.noRelevantJobs"),
        no_jobs_after_structured_filters: t("searchProgress.notice.structuredFilters"),
        degraded_plan_fallback: t("searchProgress.notice.fallback"),
    };
    const errorNoticeByReason = {
        search_execution_failed: t("searchProgress.error.execution"),
        pipeline_processing_failed: t("searchProgress.error.processing"),
        job_persistence_failed: t("searchProgress.error.persistence"),
        pipeline_timeout: t("searchProgress.error.timeout"),
        server_shutdown: t("searchProgress.error.shutdown"),
        llm_plan_error: t("searchProgress.error.plan"),
        llm_plan_rate_limited: t("searchProgress.error.busy"),
    };
    const statusNotice = isDone
        ? doneNoticeByReason[terminal_reason]
        : isError
            ? errorNoticeByReason[terminal_reason]
            : null;
    const showDebugLabel = isDone || isError;
    const debugTerminalReason = terminal_reason || "n/a";
    const debugLabel = `LLM_DEBUG state=${state} terminal_reason=${debugTerminalReason} profile_id=${profileId}`;
    const duplicateTotal = jobs_duplicates_total ?? jobs_duplicates ?? 0;
    const duplicateRuntime = jobs_duplicates_runtime ?? 0;
    const duplicateHistory = jobs_duplicates_history ?? 0;
    const duplicateCatalogConflicts = jobs_duplicates_catalog_conflicts ?? 0;

    const progressPct = _rawProgressPct;

    let analyzedJobs = [];
    if (state === "analyzing") {
        if (Array.isArray(analysis_targets) && analysis_targets.length > 0) {
            const completedCount = jobs_analyzed || 0;
            const currentIndex = analysis_current_index || 0;
            analyzedJobs = analysis_targets.map((entry, index) => {
                const itemIndex = index + 1;
                const title = typeof entry === 'string'
                    ? entry
                    : entry?.title || t("searchProgress.target", { index: itemIndex });
                const isDone = itemIndex <= completedCount;
                const isCurrent = !isDone && itemIndex === currentIndex;
                return {
                    idx: itemIndex,
                    total: analysis_targets.length,
                    title,
                    status: isDone ? 'done' : isCurrent ? 'analyzing' : 'pending'
                };
            });
        }
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
                            title={t("searchProgress.debugLabel")}
                            data-testid="llm-debug-label"
                        >
                            {debugLabel}
                        </span>
                    </div>
                )}

                {/* Stats Grid */}
                <div className="row g-3 justify-content-center">
                    {[
                        // jobs_new is updated live as jobs are saved during searching —
                        // show it with a contextual label ("Saved" while running, "New Intel" when done).
                        isRunning
                            ? { label: t("searchProgress.saved"), value: jobs_new, color: 'text-primary' }
                            : { label: t("searchProgress.newJobs"), value: jobs_new, color: 'text-white' },
                        { label: t("searchProgress.inQueue"), value: Math.max(0, (jobs_unique || 0) - (jobs_new || 0) - (jobs_skipped || 0)), color: 'text-info' },
                        {
                            label: t("searchProgress.duplicates"),
                            value: duplicateTotal,
                            color: 'text-warning',
                            detail: `R ${duplicateRuntime} H ${duplicateHistory} C ${duplicateCatalogConflicts}`,
                        },
                        { label: t("searchProgress.skipped"), value: jobs_skipped, color: 'text-secondary' },
                        { label: t("searchProgress.errors"), value: errors, color: 'text-danger' }
                    ].map((stat, i) => (
                        <div key={i} className="col-4 col-md">
                            <div className="p-3 rounded-4 bg-black-20 border border-white-5 text-center h-100 d-flex flex-column justify-content-center">
                                <div className={`display-6 fw-bold mb-0 ${stat.color}`} style={{ fontSize: '1.75rem' }}>{stat.value || 0}</div>
                                <div className="text-secondary x-small text-uppercase tracking-wide opacity-75 mt-1">{stat.label}</div>
                                {stat.detail ? (
                                    <div className="text-secondary x-small opacity-60 mt-1">{stat.detail}</div>
                                ) : null}
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
