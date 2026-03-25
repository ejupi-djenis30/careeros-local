import React from "react";

const DEFAULT_FILTERS = {
    search_profile_id: "",
    min_score: "",
    max_distance: "",
    worth_applying: "",
    sort_by: "created_at",
    sort_order: "desc",
};

export function FilterBar({ filters = DEFAULT_FILTERS, onChange, searchProfiles = [], onClear, onRefresh }) {
    const safeFilters = { ...DEFAULT_FILTERS, ...filters };
    const availableProfiles = Array.isArray(searchProfiles) ? searchProfiles : [];

    const handleChange = (key, value) => {
        onChange({ ...safeFilters, [key]: value });
    };

    const isGlobal = !safeFilters.search_profile_id;

    return (
        <div className="d-flex flex-wrap gap-3 align-items-center">
            {/* Filter Group: Scope */}
            <div className="d-flex align-items-center bg-primary bg-opacity-10 border border-primary rounded-pill px-2">
                <i className="bi bi-radar text-primary ms-1 me-2 text-primary"></i>
                <select
                    className="form-select form-select-sm border-0 bg-transparent text-primary fw-bold py-0 shadow-none ps-0"
                    value={safeFilters.search_profile_id || ""}
                    onChange={(e) => handleChange("search_profile_id", e.target.value ? Number(e.target.value) : "")}
                    style={{ width: 'auto', minWidth: '150px' }}
                >
                    <option value="" className="bg-dark text-white">Global Dashboard</option>
                    {availableProfiles.map(p => (
                        <option key={p.id} value={p.id} className="bg-dark text-white">
                            Search: {p.name || p.role_description || 'Unknown'}
                        </option>
                    ))}
                </select>
            </div>

            {/* AI Filters (Only when scoped) */}
            {!isGlobal && (
                <>
                    <div className="d-flex align-items-center bg-white-5 rounded-pill px-2 border border-white-5" title="Minimum Score">
                        <i className="bi bi-bar-chart-line text-secondary px-2"></i>
                        <select
                            className="form-select form-select-sm border-0 bg-transparent text-white py-0 shadow-none"
                            value={safeFilters.min_score || ""}
                            onChange={(e) => handleChange("min_score", e.target.value ? Number(e.target.value) : "")}
                            style={{ width: 'auto', minWidth: '85px' }}
                        >
                            <option value="" className="bg-dark text-white">Any</option>
                            <option value="50" className="bg-dark text-white">50%+</option>
                            <option value="70" className="bg-dark text-white">70%+</option>
                            <option value="85" className="bg-dark text-white">85%+</option>
                            <option value="90" className="bg-dark text-white">90%+</option>
                        </select>
                    </div>

                    <div className="d-flex align-items-center bg-white-5 rounded-pill px-2 border border-white-5" title="Maximum Distance">
                        <i className="bi bi-geo-alt text-secondary px-2"></i>
                        <select
                            className="form-select form-select-sm border-0 bg-transparent text-white py-0 shadow-none"
                            value={safeFilters.max_distance || ""}
                            onChange={(e) => handleChange("max_distance", e.target.value ? Number(e.target.value) : "")}
                            style={{ width: 'auto', minWidth: '85px' }}
                        >
                            <option value="" className="bg-dark text-white">Any</option>
                            <option value="10" className="bg-dark text-white">10 km</option>
                            <option value="25" className="bg-dark text-white">25 km</option>
                            <option value="50" className="bg-dark text-white">50 km</option>
                            <option value="100" className="bg-dark text-white">100 km</option>
                        </select>
                    </div>

                    {/* Filter Toggle: Top Picks */}
                    <button 
                        type="button"
                        className={`btn btn-sm rounded-pill px-3 d-flex align-items-center gap-2 border transition-all ${safeFilters.worth_applying ? 'bg-primary-10 border-primary text-primary' : 'bg-white-5 border-white-5 text-secondary hover-bg-white-10'}`}
                        onClick={() => handleChange("worth_applying", !safeFilters.worth_applying)}
                    >
                        <i className={`bi ${safeFilters.worth_applying ? 'bi-star-fill' : 'bi-star'}`}></i>
                        <span className="fw-medium">Top Picks</span>
                    </button>

                    {/* Active Precision Filters badges */}
                    {(() => {
                        const activeProfile = availableProfiles.find(p => p.id === Number(safeFilters.search_profile_id));
                        if (!activeProfile) return null;
                        const langs = activeProfile.preferred_languages || [];
                        const domains = activeProfile.preferred_domains || [];
                        const remoteOnly = activeProfile.remote_only;
                        const salaryMin = activeProfile.salary_min_chf;
                        if (!langs.length && !domains.length && !remoteOnly && !salaryMin) return null;
                        return (
                            <div className="d-flex align-items-center gap-1 flex-wrap" title="Active precision filters for this search">
                                <i className="bi bi-funnel-fill text-secondary opacity-50 x-small"></i>
                                {langs.map(l => (
                                    <span key={l} className="badge bg-info text-dark" style={{ fontSize: "0.65rem" }}>{l.toUpperCase()}</span>
                                ))}
                                {domains.map(d => (
                                    <span key={d} className="badge bg-primary" style={{ fontSize: "0.65rem" }}>{d}</span>
                                ))}
                                {remoteOnly && <span className="badge bg-success" style={{ fontSize: "0.65rem" }}>Remote</span>}
                                {salaryMin && <span className="badge bg-warning text-dark" style={{ fontSize: "0.65rem" }}>CHF {Number(salaryMin).toLocaleString()}+</span>}
                            </div>
                        );
                    })()}
                </>
            )}

            <div className="vr mx-1 bg-white opacity-10"></div>

            <div className="d-flex align-items-center ms-auto">
                <select
                    className="form-select form-select-sm bg-white-5 text-white border-white-5 rounded-pill ps-3"
                    value={`${safeFilters.sort_by}:${safeFilters.sort_order}`}
                    onChange={(e) => {
                        const [by, order] = e.target.value.split(":");
                        onChange({ ...safeFilters, sort_by: by, sort_order: order });
                    }}
                    style={{ width: 'auto', minWidth: '120px' }}
                >
                    <option value="created_at:desc" className="bg-dark">Newest</option>
                    <option value="created_at:asc" className="bg-dark">Oldest</option>
                    {!isGlobal && <option value="affinity_score:desc" className="bg-dark">Best Match</option>}
                    <option value="distance_km:asc" className="bg-dark">Closest</option>
                </select>

                {/* Refresh Data */}
                {onRefresh && (
                    <button
                        type="button"
                        className="btn btn-icon btn-secondary rounded-circle ms-2"
                        onClick={onRefresh}
                        title="Refresh Data"
                    >
                        <i className="bi bi-arrow-clockwise"></i>
                    </button>
                )}

                {/* Clear Filters */}
                <button
                    type="button"
                    className="btn btn-icon btn-secondary rounded-circle ms-2"
                    onClick={onClear}
                    title="Clear filters"
                >
                    <i className="bi bi-x-lg"></i>
                </button>
            </div>
        </div>
    );
}
