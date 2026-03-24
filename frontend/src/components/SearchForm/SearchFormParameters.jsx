import React from "react";

export function SearchFormParameters({ profile, handleChange }) {
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
