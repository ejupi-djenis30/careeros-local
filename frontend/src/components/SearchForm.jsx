import React, { useEffect, useState } from "react";
import { SearchService } from "../services/search";
import { CareerService } from "../services/career";
import { useToast } from "../context/ToastContext";
import { SearchFormCoreInputs } from "./SearchForm/SearchFormCoreInputs";
import { SearchFormParameters } from "./SearchForm/SearchFormParameters";
import { SearchFormAdvanced } from "./SearchForm/SearchFormAdvanced";
import { SearchProfileSource } from "./SearchForm/SearchProfileSource";
import { normalizePrefillProfile } from "./SearchForm/searchFormUtils";
import { useI18n } from "../i18n/useI18n";

const INITIAL_PROFILE = {
    name: "",
    role_description: "",
    location_filter: "",
    workload_filter: "80-100",
    contract_type: "any",
    posted_within_days: 30,
    max_distance: 50,
    latitude: null,
    longitude: null,
    profile_source: "career_vault",
    cv_content: "",
    schedule_enabled: false,
    schedule_interval_hours: 24,
    max_queries: "",
    max_occupation_queries: "",
    max_keyword_queries: "",
    force_regenerate_cv_summary: false,
    force_regenerate_queries: false,
    preferred_languages: [],
    remote_only: false,
    salary_min_chf: "",
};

const ADVANCED_ERROR_KEYS = new Set([
    "posted_within_days",
    "max_distance",
    "schedule_interval_hours",
    "name",
]);

const ERROR_TARGETS = {
    role_description: "search-role-description",
    location_filter: "search-location",
    profile_source: "profile-source-career-vault",
    posted_within_days: "search-posted-days",
    max_distance: "search-max-distance",
    schedule_interval_hours: "search-schedule-interval",
    name: "search-name",
};

export function SearchForm({ onStartSearch, isLoading, prefill }) {
    const { showToast } = useToast();
    const { language, t } = useI18n();
    const locale = language === "it" ? "it-IT" : "en-GB";
    const [existingNames, setExistingNames] = useState([]);
    const [profile, setProfile] = useState(INITIAL_PROFILE);
    const [vault, setVault] = useState({ status: "loading", revision: null, confirmedFacts: 0 });
    const [vaultReload, setVaultReload] = useState(0);
    const [isUploading, setIsUploading] = useState(false);
    const [errors, setErrors] = useState({});
    const [advancedOpen, setAdvancedOpen] = useState(false);

    useEffect(() => {
        if (prefill) {
            setProfile(prev => ({ ...prev, ...normalizePrefillProfile(prefill) }));
        }
    }, [prefill]);

    useEffect(() => {
        const controller = new AbortController();
        setVault({ status: "loading", revision: null, confirmedFacts: 0 });
        CareerService.getProfile({ signal: controller.signal, suppressGlobalError: true })
            .then(careerProfile => {
                const confirmedFacts = (careerProfile?.facts || [])
                    .filter(fact => fact?.verification_status === "confirmed")
                    .length;
                setVault({
                    status: careerProfile && confirmedFacts > 0 ? "ready" : "missing",
                    revision: careerProfile?.revision ?? null,
                    confirmedFacts,
                });
            })
            .catch(error => {
                if (error?.name === "AbortError") return;
                const status = error?.status ?? error?.response?.status;
                setVault({ status: status === 404 ? "missing" : "error", revision: null, confirmedFacts: 0 });
            });
        return () => controller.abort();
    }, [vaultReload]);

    useEffect(() => {
        SearchService.getProfileSummaries()
            .then(profiles => {
                const names = (profiles || [])
                    .map(item => (item.name || "").trim().toLowerCase())
                    .filter(Boolean);
                setExistingNames(names);
            })
            .catch(error => {
                showToast({
                    messageKey: "searchForm.loadNamesFailed",
                    variables: { error: error?.message || { messageKey: "common.unknownError" } },
                });
            });
    }, [showToast]);

    const clearError = (key) => {
        setErrors(current => {
            if (!current[key] && !current.submit) return current;
            const next = { ...current };
            delete next[key];
            delete next.submit;
            return next;
        });
    };

    const handleChange = event => {
        const { name, value } = event.target;
        setProfile(current => ({ ...current, [name]: value }));
        clearError(name);
    };

    const handleLocationChange = locationData => {
        setProfile(current => ({
            ...current,
            location_filter: locationData.name,
            latitude: locationData.lat,
            longitude: locationData.lon,
        }));
        clearError("location_filter");
    };

    const handleRemoteChange = event => {
        const remoteOnly = event.target.checked;
        setProfile(current => ({
            ...current,
            remote_only: remoteOnly,
            max_distance: remoteOnly ? 0 : (Number(current.max_distance) > 0 ? current.max_distance : 50),
        }));
        clearError("max_distance");
    };

    const handleSourceChange = event => {
        const profileSource = event.target.value;
        setProfile(current => ({ ...current, profile_source: profileSource }));
        clearError("profile_source");
    };

    const handleCVUpload = async event => {
        const file = event.target.files?.[0];
        if (!file) return;
        const maxCvSize = 10 * 1024 * 1024;
        if (file.size > maxCvSize) {
            setErrors(current => ({
                ...current,
                profile_source: t("searchForm.cvTooLarge", {
                    size: (file.size / (1024 * 1024)).toLocaleString(locale, { maximumFractionDigits: 1 }),
                }),
            }));
            event.target.value = "";
            return;
        }
        setIsUploading(true);
        clearError("profile_source");
        try {
            const { text } = await SearchService.uploadCV(file);
            setProfile(current => ({ ...current, cv_content: text || "" }));
        } catch (error) {
            setErrors(current => ({
                ...current,
                profile_source: t("searchForm.cvUploadFailed", {
                    error: error?.message || t("common.unknownError"),
                }),
            }));
        } finally {
            setIsUploading(false);
            event.target.value = "";
        }
    };

    const coerceNumericValue = (value, fallback = undefined) => {
        if (value === "" || value == null) return fallback;
        const nextValue = Number(value);
        return Number.isFinite(nextValue) ? nextValue : fallback;
    };

    const focusFirstError = nextErrors => {
        const firstKey = Object.keys(nextErrors).find(key => key !== "submit");
        if (!firstKey) return;
        if (ADVANCED_ERROR_KEYS.has(firstKey)) setAdvancedOpen(true);
        window.requestAnimationFrame(() => {
            window.requestAnimationFrame(() => {
                const targetId = firstKey === "profile_source"
                    ? `profile-source-${profile.profile_source.replace("_", "-")}`
                    : ERROR_TARGETS[firstKey];
                document.getElementById(targetId)?.focus();
            });
        });
    };

    const validate = ({ postedWithinDays, maxDistance, scheduleIntervalHours }) => {
        const nextErrors = {};
        if (!profile.role_description.trim()) nextErrors.role_description = t("searchForm.validation.roleRequired");
        if (!profile.location_filter.trim()) nextErrors.location_filter = t("searchForm.validation.locationRequired");
        if (profile.profile_source === "career_vault") {
            if (vault.status === "loading") nextErrors.profile_source = t("searchForm.validation.vaultChecking");
            else if (vault.status !== "ready") nextErrors.profile_source = t("searchForm.validation.vaultNotReady");
        } else if (!profile.cv_content.trim()) {
            nextErrors.profile_source = t("searchForm.validation.cvRequired");
        }
        if (postedWithinDays < 1) nextErrors.posted_within_days = t("searchForm.validation.postedDays");
        if (maxDistance < 0) nextErrors.max_distance = t("searchForm.validation.distance");
        if (profile.schedule_enabled && scheduleIntervalHours < 1) nextErrors.schedule_interval_hours = t("searchForm.validation.schedule");
        if (profile.name.trim() && existingNames.includes(profile.name.trim().toLowerCase())) nextErrors.name = t("searchForm.validation.duplicateName");
        return nextErrors;
    };

    const handleSubmit = async event => {
        event.preventDefault();
        const postedWithinDays = coerceNumericValue(profile.posted_within_days, 30);
        const maxDistance = profile.remote_only ? 0 : coerceNumericValue(profile.max_distance, 50);
        const scheduleIntervalHours = coerceNumericValue(profile.schedule_interval_hours, 24);
        const maxQueries = profile.max_queries === "" ? -1 : coerceNumericValue(profile.max_queries, -1);
        const maxOccupationQueries = profile.max_occupation_queries === "" ? -1 : coerceNumericValue(profile.max_occupation_queries, -1);
        const maxKeywordQueries = profile.max_keyword_queries === "" ? -1 : coerceNumericValue(profile.max_keyword_queries, -1);
        const nextErrors = validate({ postedWithinDays, maxDistance, scheduleIntervalHours });

        if (Object.keys(nextErrors).length > 0) {
            setErrors(nextErrors);
            focusFirstError(nextErrors);
            return;
        }

        const { cv_content: cvContent, ...profileWithoutCv } = profile;
        const searchProfile = {
            ...profileWithoutCv,
            profile_source: profile.profile_source,
            ...(profile.profile_source === "uploaded_cv" ? { cv_content: cvContent } : {}),
            posted_within_days: postedWithinDays,
            max_distance: maxDistance,
            schedule_interval_hours: scheduleIntervalHours,
            max_queries: maxQueries,
            max_occupation_queries: maxOccupationQueries,
            max_keyword_queries: maxKeywordQueries,
            preferred_languages: profile.preferred_languages?.length ? profile.preferred_languages : undefined,
            remote_only: profile.remote_only || undefined,
            salary_min_chf: profile.salary_min_chf !== "" && profile.salary_min_chf != null
                ? Number(profile.salary_min_chf)
                : undefined,
        };

        setErrors({});
        try {
            const result = await onStartSearch(searchProfile);
            if (result?.error) setErrors({ submit: result.error });
        } catch (error) {
            setErrors({ submit: error?.message || t("searchForm.validation.submitFailed") });
        }
    };

    return (
        <div className="search-brief animate-fade-in">
            <form onSubmit={handleSubmit} noValidate>
                <header className="search-brief__header">
                    <div className="search-brief__mark" aria-hidden="true"><i className="bi bi-search" /></div>
                    <div>
                        <p className="search-section-label">{t("searchForm.eyebrow")}</p>
                        <h2>{t("searchForm.title")}</h2>
                        <p>{t("searchForm.subtitle")}</p>
                    </div>
                </header>

                <div className="search-brief__base">
                    <SearchFormCoreInputs
                        profile={profile}
                        handleChange={handleChange}
                        handleLocationChange={handleLocationChange}
                        handleRemoteChange={handleRemoteChange}
                        errors={errors}
                    />
                    <SearchProfileSource
                        source={profile.profile_source}
                        onSourceChange={handleSourceChange}
                        vault={vault}
                        onRetryVault={() => setVaultReload(value => value + 1)}
                        cvReady={Boolean(profile.cv_content)}
                        isUploading={isUploading}
                        onUpload={handleCVUpload}
                        error={errors.profile_source}
                    />
                </div>

                <details className="search-advanced" open={advancedOpen} onToggle={event => setAdvancedOpen(event.currentTarget.open)}>
                    <summary>
                        <span>
                            <strong>{t("searchForm.advanced")}</strong>
                            <small>{t("searchForm.advancedCopy")}</small>
                        </span>
                        <i className="bi bi-chevron-down" aria-hidden="true" />
                    </summary>
                    <div className="search-advanced__content">
                        <SearchFormParameters profile={profile} handleChange={handleChange} setProfile={setProfile} errors={errors} />
                        <SearchFormAdvanced profile={profile} handleChange={handleChange} setProfile={setProfile} existingNames={existingNames} errors={errors} />
                    </div>
                </details>

                <footer className="search-brief__footer">
                    <div className="search-brief__privacy">
                        <i className="bi bi-shield-lock" aria-hidden="true" />
                        <span>{t("searchForm.localCopy")}</span>
                    </div>
                    <div className="search-brief__action">
                        {errors.submit && <p className="field-error" role="alert">{errors.submit}</p>}
                        <button type="submit" disabled={isLoading || isUploading} className="button button--primary search-brief__submit">
                            {isLoading ? <span className="spinner-border spinner-border-sm" aria-hidden="true" /> : <i className="bi bi-arrow-right" aria-hidden="true" />}
                            {isLoading ? t("searchForm.starting") : t("searchForm.start")}
                        </button>
                    </div>
                </footer>
            </form>
        </div>
    );
}
