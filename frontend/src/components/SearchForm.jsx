import React, { useState, useEffect } from "react";
import { SearchService } from "../services/search";
import { useToast } from "../context/ToastContext";
import { SearchFormCoreInputs } from "./SearchForm/SearchFormCoreInputs";
import { SearchFormParameters } from "./SearchForm/SearchFormParameters";
import { SearchFormAdvanced } from "./SearchForm/SearchFormAdvanced";

export function SearchForm({ onStartSearch, isLoading, prefill }) {
    const { showToast } = useToast();
    const [profile, setProfile] = useState({
        name: "",
        role_description: "",
        search_strategy: "",
        location_filter: "",
        workload_filter: "80-100",
        posted_within_days: 30,
        max_distance: 50,
        latitude: null,
        longitude: null,
        cv_content: "",
        schedule_enabled: false,
        schedule_interval_hours: 24,
        max_queries: "",             // Empty means unlimited
        max_occupation_queries: "",  // Empty means AI decides
        max_keyword_queries: "",     // Empty means AI decides
        // Feature 3: force-regeneration flags (only used on re-run)
        force_regenerate_cv_summary: false,
        force_regenerate_queries: false,
        // Precision filters (hard enforcement)
        preferred_languages: [],
        preferred_domains: [],
        remote_only: false,
        salary_min_chf: "",
        workload_min: "",
        workload_max: "",
        hard_max_distance_km: "",
    });

    useEffect(() => {
        if (prefill) {
            // eslint-disable-next-line react-hooks/set-state-in-effect
            setProfile(prev => ({
                ...prev,
                ...prefill,
            }));
        }
    }, [prefill]);

    const handleChange = (e) => {
        const { name, value } = e.target;
        setProfile(prev => ({ ...prev, [name]: value }));
    };

    const handleLocationChange = (locationData) => {
        setProfile(prev => ({
            ...prev,
            location_filter: locationData.name,
            latitude: locationData.lat,
            longitude: locationData.lon
        }));
    };

    const handleCVUpload = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        try {
            const { text } = await SearchService.uploadCV(file);
            setProfile(prev => ({ ...prev, cv_content: text }));
        } catch (err) {
            showToast("Failed to upload CV: " + err.message);
        }
    };

    const handleSubmit = (e) => {
        e.preventDefault();

        if (!profile.cv_content) {
            showToast("Please upload your CV first. It is required for AI-powered search.");
            return;
        }
        if (!profile.role_description.trim()) {
            showToast("Please describe what you are looking for (Role Description).");
            return;
        }
        if (!profile.location_filter.trim()) {
            showToast("Please enter a location.");
            return;
        }
        if (profile.latitude == null || profile.longitude == null) {
            showToast("Invalid location: please select a valid location from the suggestions.");
            return;
        }

        const { scrape_mode: _legacyScrapeMode, ...profilePayload } = profile;
        const searchProfile = {
            ...profilePayload,
            max_queries: profile.max_queries === "" ? -1 : profile.max_queries,
            max_occupation_queries: profile.max_occupation_queries === "" ? -1 : profile.max_occupation_queries,
            max_keyword_queries: profile.max_keyword_queries === "" ? -1 : profile.max_keyword_queries,
            // Precision filters: send only when user made a conscious selection
            preferred_languages: profile.preferred_languages?.length ? profile.preferred_languages : undefined,
            preferred_domains: profile.preferred_domains?.length ? profile.preferred_domains : undefined,
            remote_only: profile.remote_only || undefined,
            salary_min_chf: profile.salary_min_chf !== "" && profile.salary_min_chf != null ? Number(profile.salary_min_chf) : undefined,
            workload_min: profile.workload_min !== "" && profile.workload_min != null ? Number(profile.workload_min) : undefined,
            workload_max: profile.workload_max !== "" && profile.workload_max != null ? Number(profile.workload_max) : undefined,
            hard_max_distance_km: profile.hard_max_distance_km !== "" && profile.hard_max_distance_km != null ? Number(profile.hard_max_distance_km) : undefined,
        };

        onStartSearch(searchProfile);
    };

    return (
        <div className="animate-fade-in w-100 h-100 d-flex flex-column">
            <div className="glass-panel p-3 p-lg-4 h-100 d-flex flex-column">
                <form onSubmit={handleSubmit} className="d-flex flex-column h-100">
                    
                    {/* Header */}
                    <div className="d-flex flex-column flex-md-row align-items-md-center justify-content-between mb-4 pb-3 border-bottom border-white-10 gap-3">
                        <div className="d-flex align-items-center gap-3">
                            <div className="d-flex align-items-center justify-content-center p-2 rounded-circle bg-primary-10 border border-primary-20 shadow-glow" style={{width: 42, height: 42}}>
                                <i className="bi bi-rocket-takeoff-fill text-primary fs-5"></i>
                            </div>
                            <div>
                                <h4 className="fw-bold mb-0 text-white leading-tight">New Search Consideration</h4>
                                <div className="text-secondary x-small">Configure AI parameters</div>
                            </div>
                        </div>
                        
                        <div className="d-flex align-items-center gap-2 align-self-stretch align-self-md-auto">
                             <button
                                type="submit"
                                disabled={isLoading}
                                className="btn btn-primary rounded-pill px-4 shadow-glow hover-scale fw-bold d-flex align-items-center justify-content-center gap-2 w-100 w-md-auto"
                            >
                                {isLoading ? (
                                    <span className="spinner-border spinner-border-sm"></span>
                                ) : (
                                    <i className="bi bi-play-fill fs-5"></i>
                                )}
                                Start Search
                            </button>
                        </div>
                    </div>

                    {/* Main Grid content */}
                    <div className="row g-4 flex-grow-1">
                        
                        {/* Column 1: Core Inputs */}
                        <SearchFormCoreInputs 
                            profile={profile} 
                            handleChange={handleChange} 
                            handleLocationChange={handleLocationChange} 
                            handleCVUpload={handleCVUpload} 
                        />

                        {/* Column 2: Parameters */}
                        <SearchFormParameters 
                            profile={profile} 
                            handleChange={handleChange}
                            setProfile={setProfile}
                        />

                         {/* Column 3: Advanced & Logistics */}
                         <SearchFormAdvanced 
                            profile={profile} 
                            handleChange={handleChange} 
                            setProfile={setProfile} 
                        />
                    </div>
                </form>
            </div>
        </div>
    );
}
