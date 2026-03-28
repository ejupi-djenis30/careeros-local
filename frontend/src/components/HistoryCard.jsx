import React, { memo } from 'react';

export const HistoryCard = memo(function HistoryCard({ profile, onStartSearch, onStartSearchWithOptions, onUseAsTemplate, onSaveAsSchedule, isLoading }) {
    const displayName = (profile.name && profile.name.trim()) || "Untitled Search";
    const advPrefs = profile.advanced_preferences || {};
    const languages = advPrefs.preferred_languages || profile.preferred_languages || [];
    const remoteOnly = advPrefs.remote_only || profile.remote_only;
    const salaryMin = advPrefs.salary_min_chf || profile.salary_min_chf;

    return (
        <div className="glass-panel p-3 px-md-4 py-md-3 hover-bg-white-5 transition-colors group">
            {/* Top row: Icon + Title + Actions */}
            <div className="d-flex align-items-center gap-3 mb-2">
                {/* Icon */}
                <div className="flex-shrink-0">
                    <div className={`rounded-circle d-flex align-items-center justify-content-center text-white shadow-sm border border-white-10 ${profile.schedule_enabled ? 'bg-success' : 'bg-primary'}`} style={{ width: 42, height: 42 }}>
                        <i className={`bi ${profile.schedule_enabled ? 'bi-robot' : 'bi-search'} fs-5`}></i>
                    </div>
                </div>

                {/* Content */}
                <div className="flex-grow-1 min-w-0">
                    {/* Title */}
                    <h6 className="mb-0 fw-bold text-white text-truncate lh-sm" title={displayName}>{displayName}</h6>
                </div>

                {/* Actions */}
                <div className="flex-shrink-0">
                    <div className="d-flex align-items-center gap-2 opacity-75 group-hover-opacity-100 transition-opacity flex-wrap justify-content-end">
                        <button
                            className="btn btn-sm btn-primary px-3 rounded-pill fw-medium shadow-glow d-flex align-items-center justify-content-center"
                            onClick={() => onStartSearch?.(profile)}
                            disabled={isLoading}
                            title="Rerun Search"
                        >
                            {isLoading
                                ? <><span className="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Running…</>
                                : <><i className="bi bi-play-fill me-1"></i> Run</>
                            }
                        </button>

                        <button
                            className="btn btn-sm btn-icon btn-secondary rounded-circle d-flex align-items-center justify-content-center"
                            onClick={() => onStartSearchWithOptions?.(profile, { force_regenerate_queries: true })}
                            disabled={isLoading}
                            title="Rerun with fresh queries only"
                            aria-label="Rerun with fresh queries only"
                        >
                            <i className="bi bi-diagram-3"></i>
                        </button>

                        <button
                            className="btn btn-sm btn-icon btn-secondary rounded-circle d-flex align-items-center justify-content-center"
                            onClick={() => onStartSearchWithOptions?.(profile, { force_regenerate_cv_summary: true })}
                            disabled={isLoading}
                            title="Rerun with fresh CV summary only"
                            aria-label="Rerun with fresh CV summary only"
                        >
                            <i className="bi bi-file-earmark-arrow-up"></i>
                        </button>

                        <button
                            className="btn btn-sm btn-icon btn-warning text-dark rounded-circle d-flex align-items-center justify-content-center"
                            onClick={() => onStartSearchWithOptions?.(profile, { force_regenerate_cv_summary: true, force_regenerate_queries: true })}
                            disabled={isLoading}
                            title="Rerun with fresh CV summary and queries (full refresh)"
                            aria-label="Rerun with fresh CV summary and queries"
                        >
                            <i className="bi bi-arrow-repeat"></i>
                        </button>

                        <button
                            className="btn btn-sm btn-icon btn-secondary rounded-circle d-flex align-items-center justify-content-center"
                            onClick={() => onUseAsTemplate?.(profile)}
                            disabled={isLoading}
                            title="New Search from this"
                        >
                            <i className="bi bi-copy"></i>
                        </button>

                        {!profile.schedule_enabled && (
                            <button
                                className="btn btn-sm btn-icon btn-secondary rounded-circle d-flex align-items-center justify-content-center"
                                onClick={() => onSaveAsSchedule?.(profile)}
                                disabled={isLoading}
                                title="Add to Schedule"
                            >
                                <i className="bi bi-clock"></i>
                            </button>
                        )}
                    </div>
                </div>
            </div>
            {/* Search parameters row */}
            <div className="d-flex flex-wrap column-gap-3 row-gap-1 small text-white-50 lh-sm mb-2">
                <span className="d-flex align-items-center" title="Location">
                    <i className="bi bi-geo-alt me-1 text-primary"></i>
                    {profile.location_filter || "Any Location"}
                </span>
                <span className="d-flex align-items-center" title="Time range">
                    <i className="bi bi-calendar me-1 text-primary"></i>
                    {`Last ${profile.posted_within_days} days`}
                </span>
                {profile.workload_filter && (
                    <span className="d-flex align-items-center" title="Workload">
                        <i className="bi bi-briefcase me-1 text-primary"></i>
                        {profile.workload_filter}%
                    </span>
                )}
                {profile.max_distance && (
                    <span className="d-flex align-items-center" title="Max distance">
                        <i className="bi bi-signpost-2 me-1 text-primary"></i>
                        {profile.max_distance}km
                    </span>
                )}
                {profile.contract_type && profile.contract_type !== "any" && (
                    <span className="d-flex align-items-center" title="Contract type">
                        <i className="bi bi-file-text me-1 text-primary"></i>
                        {profile.contract_type}
                    </span>
                )}
                {languages.length > 0 && (
                    <span className="d-flex align-items-center gap-1" title="Preferred languages">
                        <i className="bi bi-translate me-1 text-primary"></i>
                        {languages.map(l => l.toUpperCase()).join(", ")}
                    </span>
                )}
                {remoteOnly && (
                    <span className="d-flex align-items-center text-info" title="Remote only">
                        <i className="bi bi-house me-1"></i>
                        Remote
                    </span>
                )}
                {salaryMin && (
                    <span className="d-flex align-items-center" title="Minimum salary">
                        <i className="bi bi-cash me-1 text-primary"></i>
                        CHF {Number(salaryMin).toLocaleString()}+
                    </span>
                )}
                {profile.schedule_enabled && (
                    <span className="text-success fw-medium d-flex align-items-center">
                        <i className="bi bi-check-circle-fill me-1"></i>
                        Auto every {profile.schedule_interval_hours ?? 24}h
                    </span>
                )}
            </div>

            {/* Role description (multi-line, word-wrap) */}
            {profile.role_description && (
                <div
                    className="text-secondary x-small lh-base"
                    style={{ overflowWrap: 'break-word', wordBreak: 'break-word', whiteSpace: 'normal', maxHeight: '4.5em', overflow: 'hidden' }}
                    title={profile.role_description}
                >
                    {profile.role_description}
                </div>
            )}
        </div>
    );
});
