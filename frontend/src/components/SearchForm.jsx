import React, { useState, useEffect } from "react";
import { SearchService } from "../services/search";
import { useToast } from "../context/ToastContext";
import { SearchFormCoreInputs } from "./SearchForm/SearchFormCoreInputs";
import { SearchFormParameters } from "./SearchForm/SearchFormParameters";
import { SearchFormAdvanced } from "./SearchForm/SearchFormAdvanced";
import { normalizePrefillProfile } from "./SearchForm/searchFormUtils";
import { useI18n } from "../i18n/useI18n";

export function SearchForm({ onStartSearch, isLoading, prefill }) {
    const { showToast } = useToast();
    const { language, t } = useI18n();
    const locale = language === "it" ? "it-IT" : "en-GB";
    const [existingNames, setExistingNames] = useState([]);
    const [profile, setProfile] = useState({
        name: "",
        role_description: "",
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
        // Precision filters
        preferred_languages: [],
        remote_only: false,
        salary_min_chf: "",
    });

    useEffect(() => {
        if (prefill) {
            // eslint-disable-next-line react-hooks/set-state-in-effect
            setProfile(prev => ({
                ...prev,
                ...normalizePrefillProfile(prefill),
            }));
        }
    }, [prefill]);

    useEffect(() => {
        SearchService.getProfiles()
            .then(profiles => {
                const names = (profiles || [])
                    .map(p => (p.name || "").trim().toLowerCase())
                    .filter(Boolean);
                setExistingNames(names);
            })
            .catch((error) => {
                showToast(t("searchForm.loadNamesFailed", { error: error?.message || t("common.unknownError") }));
            });
    }, [showToast, t]);

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
        const MAX_CV_SIZE = 10 * 1024 * 1024; // 10 MB — must match backend MAX_UPLOAD_FILE_SIZE
        if (file.size > MAX_CV_SIZE) {
            showToast(t("searchForm.cvTooLarge", {
                size: (file.size / (1024 * 1024)).toLocaleString(locale, { maximumFractionDigits: 1 }),
            }));
            e.target.value = "";
            return;
        }
        try {
            const { text } = await SearchService.uploadCV(file);
            setProfile(prev => ({ ...prev, cv_content: text }));
        } catch (err) {
            showToast(t("searchForm.cvUploadFailed", { error: err?.message || String(err) || t("common.unknownError") }));
        }
    };

    const coerceNumericValue = (value, fallback = undefined) => {
        if (value === "" || value == null) return fallback;
        const nextValue = Number(value);
        return Number.isFinite(nextValue) ? nextValue : fallback;
    };

    const handleSubmit = (e) => {
        e.preventDefault();

        const postedWithinDays = coerceNumericValue(profile.posted_within_days, 30);
        const maxDistance = coerceNumericValue(profile.max_distance, 50);
        const scheduleIntervalHours = coerceNumericValue(profile.schedule_interval_hours, 24);
        const maxQueries = profile.max_queries === "" ? -1 : coerceNumericValue(profile.max_queries, -1);
        const maxOccupationQueries = profile.max_occupation_queries === "" ? -1 : coerceNumericValue(profile.max_occupation_queries, -1);
        const maxKeywordQueries = profile.max_keyword_queries === "" ? -1 : coerceNumericValue(profile.max_keyword_queries, -1);

        if (!profile.cv_content) {
            showToast(t("searchForm.validation.cvRequired"));
            return;
        }
        if (!profile.role_description.trim()) {
            showToast(t("searchForm.validation.roleRequired"));
            return;
        }
        if (!profile.location_filter.trim()) {
            showToast(t("searchForm.validation.locationRequired"));
            return;
        }
        if (postedWithinDays < 1) {
            showToast(t("searchForm.validation.postedDays"));
            return;
        }
        if (maxDistance < 0) {
            showToast(t("searchForm.validation.distance"));
            return;
        }
        if (profile.schedule_enabled && scheduleIntervalHours < 1) {
            showToast(t("searchForm.validation.schedule"));
            return;
        }
        if (profile.remote_only && maxDistance > 0) {
            showToast(t("searchForm.validation.remoteDistance"));
            return;
        }
        if (profile.latitude == null || profile.longitude == null) {
            showToast(t("searchForm.validation.invalidLocation"));
            return;
        }
        if (profile.name.trim() && existingNames.includes(profile.name.trim().toLowerCase())) {
            showToast(t("searchForm.validation.duplicateName"));
            return;
        }

        const searchProfile = {
            ...profile,
            posted_within_days: postedWithinDays,
            max_distance: maxDistance,
            schedule_interval_hours: scheduleIntervalHours,
            max_queries: maxQueries,
            max_occupation_queries: maxOccupationQueries,
            max_keyword_queries: maxKeywordQueries,
            preferred_languages: profile.preferred_languages?.length ? profile.preferred_languages : undefined,
            remote_only: profile.remote_only || undefined,
            salary_min_chf: profile.salary_min_chf !== "" && profile.salary_min_chf != null ? Number(profile.salary_min_chf) : undefined,
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
                                <h4 className="fw-bold mb-0 text-white leading-tight">{t("searchForm.title")}</h4>
                                <div className="text-secondary x-small">{t("searchForm.subtitle")}</div>
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
                                {t("searchForm.start")}
                            </button>
                        </div>
                    </div>

                    {/* Main Grid content */}
                    <div className="row g-4 flex-grow-1 align-content-start">

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
                            existingNames={existingNames}
                        />
                    </div>
                </form>
            </div>
        </div>
    );
}
