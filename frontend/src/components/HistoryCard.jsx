import React from 'react';

export function HistoryCard({ profile, onStartSearch, onStartSearchWithOptions, onUseAsTemplate, onSaveAsSchedule }) {
    return (
        <div className="glass-panel p-3 px-md-4 py-md-3 hover-bg-white-5 transition-colors group">
            <div className="d-flex flex-column flex-md-row align-items-md-center gap-3">
                {/* Icon */}
                <div className="flex-shrink-0 d-flex align-items-center">
                    <div className={`rounded-circle d-flex align-items-center justify-content-center text-white shadow-sm border border-white-10 ${profile.schedule_enabled ? 'bg-success' : 'bg-primary'}`} style={{ width: 42, height: 42 }}>
                        <i className={`bi ${profile.schedule_enabled ? 'bi-robot' : 'bi-search'} fs-5`}></i>
                    </div>
                </div>

                {/* Main Info */}
                <div className="flex-grow-1 min-w-0 d-flex flex-column justify-content-center" style={{ overflow: 'hidden' }}>
                    <h6 className="mb-0 fw-bold text-white text-truncate lh-sm" title={profile.role_description}>{profile.role_description}</h6>
                    <div className="d-flex flex-wrap gap-3 small text-white-50 mt-1 lh-sm">
                        <span className="d-flex align-items-center" title="Location">
                            <i className="bi bi-geo-alt me-1 text-primary"></i>
                            {profile.location_filter || "Any Location"}
                        </span>
                        <span className="d-flex align-items-center" title="Time range">
                            <i className="bi bi-calendar me-1 text-primary"></i>
                            {`Last ${profile.posted_within_days} days`}
                        </span>
                        {profile.schedule_enabled && (
                            <span className="text-success fw-medium d-flex align-items-center">
                                <i className="bi bi-check-circle-fill me-1"></i>
                                {`Auto-runs every ${profile.schedule_interval_hours}h`}
                            </span>
                        )}
                    </div>
                </div>

                {/* Actions */}
                <div className="flex-shrink-0 d-flex align-items-center justify-content-end mt-2 mt-md-0">
                    <div className="d-flex align-items-center gap-2 opacity-75 group-hover-opacity-100 transition-opacity flex-wrap justify-content-end">
                        <button
                            className="btn btn-sm btn-primary px-3 rounded-pill fw-medium shadow-glow d-flex align-items-center justify-content-center"
                            onClick={() => onStartSearch?.(profile)}
                            title="Rerun Search"
                        >
                            <i className="bi bi-play-fill me-1"></i> Run
                        </button>

                        <button
                            className="btn btn-sm btn-icon btn-secondary rounded-circle d-flex align-items-center justify-content-center"
                            onClick={() => onStartSearchWithOptions?.(profile, { force_regenerate_queries: true })}
                            title="Rerun with fresh queries"
                        >
                            <i className="bi bi-diagram-3"></i>
                        </button>

                        <button
                            className="btn btn-sm btn-icon btn-secondary rounded-circle d-flex align-items-center justify-content-center"
                            onClick={() => onStartSearchWithOptions?.(profile, { force_regenerate_cv_summary: true })}
                            title="Rerun with fresh CV summary"
                        >
                            <i className="bi bi-file-earmark-arrow-up"></i>
                        </button>

                        <button
                            className="btn btn-sm btn-icon btn-secondary rounded-circle d-flex align-items-center justify-content-center"
                            onClick={() => onStartSearchWithOptions?.(profile, { force_regenerate_cv_summary: true, force_regenerate_queries: true })}
                            title="Rerun with fresh CV summary and queries"
                        >
                            <i className="bi bi-arrow-repeat"></i>
                        </button>

                        <button
                            className="btn btn-sm btn-icon btn-secondary rounded-circle d-flex align-items-center justify-content-center"
                            onClick={() => onUseAsTemplate?.(profile)}
                            title="New Search from this"
                        >
                            <i className="bi bi-copy"></i>
                        </button>

                        {!profile.schedule_enabled && (
                            <button
                                className="btn btn-sm btn-icon btn-secondary rounded-circle d-flex align-items-center justify-content-center"
                                onClick={() => onSaveAsSchedule?.(profile)}
                                title="Add to Schedule"
                            >
                                <i className="bi bi-clock"></i>
                            </button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
