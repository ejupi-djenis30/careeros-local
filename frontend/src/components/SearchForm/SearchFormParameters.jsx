import React from "react";

const LANGUAGES = [
    { code: "en", label: "EN" },
    { code: "de", label: "DE" },
    { code: "fr", label: "FR" },
    { code: "it", label: "IT" },
];

const DOMAINS = [
    { code: "backend", label: "Backend" },
    { code: "frontend", label: "Frontend" },
    { code: "fullstack", label: "Fullstack" },
    { code: "devops", label: "DevOps" },
    { code: "data", label: "Data" },
    { code: "machine-learning", label: "ML / AI" },
    { code: "mobile", label: "Mobile" },
    { code: "cloud", label: "Cloud" },
    { code: "embedded", label: "Embedded" },
];

export function SearchFormParameters({ profile, handleChange, setProfile }) {
    const toggleItem = (field, code) => {
        setProfile(prev => {
            const current = prev[field] || [];
            const next = current.includes(code)
                ? current.filter(v => v !== code)
                : [...current, code];
            return { ...prev, [field]: next };
        });
    };

    return (
        <div className="col-lg-4 d-flex flex-column gap-4 border-end border-white-5">
            <div className="row g-3">
                <div className="col-6">
                    <label className="form-label text-white small fw-bold text-uppercase x-small mb-2">Workload</label>
                    <select
                        name="workload_filter"
                        value={profile.workload_filter}
                        onChange={handleChange}
                        className="form-select form-select-sm bg-black-20 border-white-10 text-white"
                    >
                        <option value="80-100">80-100%</option>
                        <option value="100">100% (Full time)</option>
                        <option value="50-100">50-100%</option>
                        <option value="0-100">Any</option>
                    </select>
                </div>
                <div className="col-6">
                    <label className="form-label text-white small fw-bold text-uppercase x-small mb-2">Contract</label>
                    <select
                        name="contract_type"
                        value={profile.contract_type || "any"}
                        onChange={handleChange}
                        className="form-select form-select-sm bg-black-20 border-white-10 text-white"
                    >
                        <option value="any">Any</option>
                        <option value="permanent">Permanent</option>
                        <option value="temporary">Temporary / Freelance</option>
                    </select>
                </div>
            </div>
            
            <div className="row g-3">
                <div className="col-12">
                    <label className="form-label text-white small fw-bold text-uppercase x-small mb-2">Posted</label>
                    <select
                        name="posted_within_days"
                        value={profile.posted_within_days}
                        onChange={handleChange}
                        className="form-select form-select-sm bg-black-20 border-white-10 text-white"
                    >
                        <option value="1">Last 24h</option>
                        <option value="3">Last 3 Days</option>
                        <option value="7">Last Week</option>
                        <option value="14">Last 2 Weeks</option>
                        <option value="30">Last Month</option>
                    </select>
                </div>
            </div>
            
            <div>
                <div className="d-flex justify-content-between mb-2">
                    <label className="form-label text-white small fw-bold text-uppercase x-small mb-0">Max Distance</label>
                    <span className="x-small text-info fw-bold">{profile.max_distance} km</span>
                </div>
                <input 
                    type="range" 
                    name="max_distance" 
                    min="5" 
                    max="100" 
                    step="5" 
                    value={profile.max_distance} 
                    onChange={handleChange} 
                    className="form-range" 
                />
            </div>

            {/* Precision Filters */}
            <div className="p-3 bg-white-5 rounded-3 border border-white-5">
                <div className="x-small text-secondary fw-bold text-uppercase mb-3 d-flex align-items-center gap-2">
                    <i className="bi bi-funnel-fill"></i>Precision Filters
                </div>

                {/* Job Language chips */}
                <div className="mb-3">
                    <div className="x-small text-white fw-semibold mb-2">Job Language</div>
                    <div className="d-flex flex-wrap gap-1">
                        {LANGUAGES.map(({ code, label }) => {
                            const active = (profile.preferred_languages || []).includes(code);
                            return (
                                <button key={code} type="button"
                                    onClick={() => toggleItem("preferred_languages", code)}
                                    className={`btn btn-sm px-2 py-0 rounded-pill ${active ? "btn-info text-dark fw-bold" : "btn-outline-secondary opacity-75"}`}
                                    style={{ fontSize: "0.7rem", minWidth: 34 }}
                                >
                                    {label}
                                </button>
                            );
                        })}
                    </div>
                    <div className="x-small text-secondary opacity-60 mt-1">Leave empty to allow all languages</div>
                </div>

                {/* Tech Domain chips */}
                <div className="mb-3">
                    <div className="x-small text-white fw-semibold mb-2">Tech Domain</div>
                    <div className="d-flex flex-wrap gap-1">
                        {DOMAINS.map(({ code, label }) => {
                            const active = (profile.preferred_domains || []).includes(code);
                            return (
                                <button key={code} type="button"
                                    onClick={() => toggleItem("preferred_domains", code)}
                                    className={`btn btn-sm px-2 py-0 rounded-pill ${active ? "btn-primary fw-bold" : "btn-outline-secondary opacity-75"}`}
                                    style={{ fontSize: "0.7rem" }}
                                >
                                    {label}
                                </button>
                            );
                        })}
                    </div>
                </div>

                {/* Remote toggle + Min Salary */}
                <div className="row g-2 mb-2 align-items-end">
                    <div className="col-6 d-flex align-items-center" style={{ paddingBottom: "0.375rem" }}>
                        <div className="form-check form-switch d-flex align-items-center gap-2 ps-0 mb-0">
                            <input
                                className="form-check-input ms-0"
                                type="checkbox"
                                id="remoteOnlySwitch"
                                checked={profile.remote_only || false}
                                onChange={e => setProfile(prev => ({ ...prev, remote_only: e.target.checked }))}
                                style={{ cursor: "pointer" }}
                            />
                            <label className="form-check-label x-small text-white fw-semibold mb-0" htmlFor="remoteOnlySwitch">
                                Remote Only
                            </label>
                        </div>
                    </div>
                    <div className="col-6">
                        <label className="form-label text-secondary x-small mb-1">Min Salary (CHF/yr)</label>
                        <input
                            type="number"
                            name="salary_min_chf"
                            value={profile.salary_min_chf || ""}
                            onChange={handleChange}
                            placeholder="No min"
                            min="0"
                            step="1000"
                            className="form-control form-control-sm bg-black-20 border-white-10 text-white"
                        />
                    </div>
                </div>

                {/* Workload hard min/max + Hard distance */}
                <div className="row g-2">
                    <div className="col-4">
                        <label className="form-label text-secondary x-small mb-1">Load min %</label>
                        <input
                            type="number"
                            name="workload_min"
                            value={profile.workload_min || ""}
                            onChange={handleChange}
                            placeholder="—"
                            min="0"
                            max="100"
                            className="form-control form-control-sm bg-black-20 border-white-10 text-white"
                        />
                    </div>
                    <div className="col-4">
                        <label className="form-label text-secondary x-small mb-1">Load max %</label>
                        <input
                            type="number"
                            name="workload_max"
                            value={profile.workload_max || ""}
                            onChange={handleChange}
                            placeholder="—"
                            min="0"
                            max="100"
                            className="form-control form-control-sm bg-black-20 border-white-10 text-white"
                        />
                    </div>
                    <div className="col-4">
                        <label className="form-label text-secondary x-small mb-1">Max dist km</label>
                        <input
                            type="number"
                            name="hard_max_distance_km"
                            value={profile.hard_max_distance_km || ""}
                            onChange={handleChange}
                            placeholder="—"
                            min="0"
                            className="form-control form-control-sm bg-black-20 border-white-10 text-white"
                        />
                    </div>
                </div>
                <div className="x-small text-secondary opacity-60 mt-2">Hard limits enforced after fetching results</div>
            </div>

            <div>
                <label className="form-label text-white small fw-bold text-uppercase x-small mb-2">Extra AI Instructions</label>
                <textarea
                    name="search_strategy"
                    value={profile.search_strategy}
                    onChange={handleChange}
                    placeholder="E.g. 'Remote only', 'Avoid startups', 'Salary > 80k'..."
                    className="form-control bg-black-20 border-white-10 text-white"
                    rows="4"
                />
            </div>
        </div>
    );
}
