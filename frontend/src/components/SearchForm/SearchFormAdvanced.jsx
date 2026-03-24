import React from "react";

export function SearchFormAdvanced({ profile, handleChange, setProfile }) {
    // A profile is considered "existing" (re-run) when it has an id
    const isRerun = Boolean(profile.id);
    
    return (
        <div className="col-lg-4 d-flex flex-column gap-4">
            <div className="p-3 bg-white-5 rounded-3 border border-white-5">
                <div className="form-check form-switch d-flex align-items-center justify-content-between ps-0 mb-3">
                    <div>
                        <label className="form-check-label fw-bold text-white small mb-0" htmlFor="scheduleSwitch">Automatic Search</label>
                        <div className="x-small text-secondary opacity-75">Run this search periodically</div>
                    </div>
                    <input
                        className="form-check-input ms-2"
                        type="checkbox"
                        id="scheduleSwitch"
                        checked={profile.schedule_enabled}
                        onChange={(e) => setProfile(prev => ({ ...prev, schedule_enabled: e.target.checked }))}
                        style={{cursor: 'pointer'}}
                    />
                </div>
                
                {profile.schedule_enabled && (
                    <div className="d-flex align-items-center justify-content-between border-top border-white-10 pt-3 opacity-animation">
                        <span className="x-small text-secondary fw-bold text-uppercase">Interval</span>
                        <div className="btn-group btn-group-sm" role="group">
                            {[6, 12, 24].map(h => (
                                <button
                                    key={h}
                                    type="button"
                                    onClick={() => setProfile(prev => ({ ...prev, schedule_interval_hours: h }))}
                                    className={`btn ${profile.schedule_interval_hours == h ? 'btn-light text-dark fw-bold' : 'btn-outline-secondary'}`}
                                >
                                    {h}h
                                </button>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            <div className="mb-2">
                <label className="form-label text-white small fw-bold text-uppercase x-small mb-2">Search Title</label>
                <input
                    type="text"
                    name="name"
                    value={profile.name}
                    onChange={handleChange}
                    placeholder="E.g. Senior Python Remote"
                    className="form-control form-control-sm bg-black-20 border-white-10 text-white"
                />
                <div className="x-small text-secondary mt-1 opacity-75">Leave empty for auto-naming</div>
            </div>

            {/* Query Controls */}
            <div className="p-3 bg-white-5 rounded-3 border border-white-5">
                <div className="x-small text-secondary fw-bold text-uppercase mb-3">Query Generation</div>
                
                <div className="row g-2 mb-2">
                    <div className="col-12">
                        <label className="form-label text-white x-small fw-semibold mb-1">Max Queries (Total)</label>
                        <input
                            type="number"
                            name="max_queries"
                            value={profile.max_queries}
                            onChange={handleChange}
                            placeholder="No Limit"
                            min="1"
                            className="form-control form-control-sm bg-black-20 border-white-10 text-white"
                        />
                    </div>
                </div>
                
                <div className="row g-2">
                    <div className="col-6">
                        <label className="form-label text-secondary x-small mb-1">
                            <i className="bi bi-briefcase-fill me-1 opacity-50"></i>Occupations
                        </label>
                        <input
                            type="number"
                            name="max_occupation_queries"
                            value={profile.max_occupation_queries}
                            onChange={handleChange}
                            placeholder="AI decides"
                            min="0"
                            className="form-control form-control-sm bg-black-20 border-white-10 text-white"
                        />
                    </div>
                    <div className="col-6">
                        <label className="form-label text-secondary x-small mb-1">
                            <i className="bi bi-key-fill me-1 opacity-50"></i>Keywords
                        </label>
                        <input
                            type="number"
                            name="max_keyword_queries"
                            value={profile.max_keyword_queries}
                            onChange={handleChange}
                            placeholder="AI decides"
                            min="0"
                            className="form-control form-control-sm bg-black-20 border-white-10 text-white"
                        />
                    </div>
                </div>
                <div className="x-small text-secondary mt-2 opacity-60">
                    Set occupation/keyword counts for strict AI enforcement (up to 3 retries).
                </div>
            </div>

            {/* Scrape Mode */}
            <div className="row g-3">
                <div className="col-12">
                    <label className="form-label text-white small fw-bold text-uppercase x-small mb-2">Scrape Speed</label>
                    <select
                        name="scrape_mode"
                        value={profile.scrape_mode}
                        onChange={handleChange}
                        className="form-select form-select-sm bg-black-20 border-white-10 text-white"
                    >
                        <option value="sequential">Sequential</option>
                        <option value="immediate">Fast (Risky)</option>
                    </select>
                </div>
            </div>

            {/* Feature 3: Force Regeneration Buttons (only on re-run) */}
            {isRerun && (
                <div className="p-3 bg-warning bg-opacity-10 rounded-3 border border-warning border-opacity-20">
                    <div className="x-small text-warning fw-bold text-uppercase mb-2">
                        <i className="bi bi-lightning-charge-fill me-1"></i>Re-run Options
                    </div>
                    <div className="d-flex flex-column gap-2">
                        <button
                            type="button"
                            onClick={() => setProfile(prev => ({ ...prev, force_regenerate_cv_summary: !prev.force_regenerate_cv_summary }))}
                            className={`btn btn-sm d-flex align-items-center gap-2 ${profile.force_regenerate_cv_summary ? 'btn-warning text-dark fw-bold' : 'btn-outline-secondary'}`}
                        >
                            <i className={`bi ${profile.force_regenerate_cv_summary ? 'bi-check-circle-fill' : 'bi-arrow-clockwise'}`}></i>
                            Regenerate CV Summary
                        </button>
                        <button
                            type="button"
                            onClick={() => setProfile(prev => ({ ...prev, force_regenerate_queries: !prev.force_regenerate_queries }))}
                            className={`btn btn-sm d-flex align-items-center gap-2 ${profile.force_regenerate_queries ? 'btn-warning text-dark fw-bold' : 'btn-outline-secondary'}`}
                        >
                            <i className={`bi ${profile.force_regenerate_queries ? 'bi-check-circle-fill' : 'bi-arrow-clockwise'}`}></i>
                            Regenerate Queries
                        </button>
                    </div>
                    <div className="x-small text-warning opacity-75 mt-2">
                        By default, cached results from the last run are reused.
                    </div>
                </div>
            )}

            <div className="mt-auto p-3 rounded-3 bg-info bg-opacity-10 border border-info border-opacity-20">
                <div className="d-flex gap-2">
                    <i className="bi bi-info-circle-fill text-info mt-1"></i>
                    <div>
                        <div className="fw-bold text-white small">Pro Tip</div>
                        <div className="x-small text-info opacity-90">
                            The more specific your role description, the better the AI matching score will be.
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
