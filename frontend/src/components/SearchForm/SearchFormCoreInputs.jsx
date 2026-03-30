import React from "react";
import { LocationInput } from "../LocationInput";

export function SearchFormCoreInputs({ profile, handleChange, handleLocationChange, handleCVUpload }) {
    return (
        <div className="col-xl-5 col-lg-6 d-flex flex-column gap-4 border-end border-white-5">
            <div>
                <label className="form-label text-white small fw-bold text-uppercase x-small mb-2">Role Description <span className="text-danger">*</span></label>
                <textarea
                    name="role_description"
                    value={profile.role_description}
                    onChange={handleChange}
                    placeholder="Describe the target role, seniority, preferred companies, exclusions, schedule constraints, remote expectations, salary intent, languages, and any non-negotiables..."
                    className="form-control bg-black-20 border-white-10 text-white"
                    style={{ height: '220px', resize: 'vertical' }}
                    required
                />
                <div className="x-small text-secondary mt-2 opacity-75">
                    Put every important instruction here. There is no separate AI instructions field anymore.
                </div>
            </div>

            <div>
                <label className="form-label text-white small fw-bold text-uppercase x-small mb-2">Target Location <span className="text-danger">*</span></label>
                <LocationInput
                    location={profile.location_filter}
                    latitude={profile.latitude}
                    longitude={profile.longitude}
                    onLocationChange={handleLocationChange}
                />
            </div>

            <div className="p-3 rounded-3 border border-dashed border-secondary border-opacity-25 bg-black-20 hover-bg-white-5 transition-all mb-3 mb-lg-0">
                <label className="d-flex align-items-center justify-content-between cursor-pointer mb-0 w-100">
                    <div className="d-flex align-items-center gap-3">
                        <div className={`rounded-circle d-flex align-items-center justify-content-center ${profile.cv_content ? 'bg-success text-white' : 'bg-white-5 text-secondary'}`} style={{width: 36, height: 36}}>
                            <i className={`bi ${profile.cv_content ? 'bi-check-lg' : 'bi-upload'}`}></i>
                        </div>
                        <div>
                            <div className="fw-bold text-white small">{profile.cv_content ? 'CV Uploaded' : 'Upload CV'}</div>
                            <div className="x-small text-secondary">{profile.cv_content ? 'Ready for analysis' : 'Required for AI'}</div>
                        </div>
                    </div>
                    <input
                        type="file"
                        className="d-none"
                        accept=".pdf,.txt,.md"
                        onChange={handleCVUpload}
                    />
                    <span className="btn btn-sm btn-outline-secondary rounded-pill px-3 py-1 x-small text-uppercase">
                        {profile.cv_content ? 'Change' : 'Select'}
                    </span>
                </label>
            </div>
        </div>
    );
}
