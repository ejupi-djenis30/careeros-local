import React from "react";
import { useI18n } from "../../i18n/useI18n";

const SCHEDULE_PRESETS = [6, 12, 24];

export function SearchFormAdvanced({ profile, handleChange, setProfile, existingNames = [], errors = {} }) {
    const { language, t } = useI18n();
    const locale = language === "it" ? "it-IT" : "en-GB";
    const isRerun = profile.id != null;
    const nameIsDuplicate = profile.name.trim() && existingNames.includes(profile.name.trim().toLowerCase());

    return (
        <section className="search-advanced-panel" aria-labelledby="search-automation-title">
            <div className="search-advanced-panel__heading">
                <span className="search-advanced-panel__icon" aria-hidden="true"><i className="bi bi-gear" /></span>
                <div>
                    <p className="search-section-label">{t("searchForm.automation.eyebrow")}</p>
                    <h4 id="search-automation-title">{t("searchForm.automation.title")}</h4>
                </div>
            </div>

            <div className="search-switch-row">
                <div>
                    <label htmlFor="search-schedule">{t("searchForm.automatic")}</label>
                    <p id="search-schedule-help">{t("searchForm.automaticCopy")}</p>
                </div>
                <input
                    className="form-check-input"
                    type="checkbox"
                    role="switch"
                    id="search-schedule"
                    checked={profile.schedule_enabled}
                    onChange={(event) => setProfile(prev => ({ ...prev, schedule_enabled: event.target.checked }))}
                    aria-describedby="search-schedule-help"
                />
            </div>

            {profile.schedule_enabled && (
                <div className="search-field search-schedule-settings">
                    <label htmlFor="search-schedule-interval" className="search-field__label">{t("searchForm.intervalHours")}</label>
                    <input
                        id="search-schedule-interval"
                        type="number"
                        name="schedule_interval_hours"
                        value={profile.schedule_interval_hours}
                        onChange={handleChange}
                        min="1"
                        step="1"
                        className={`form-control form-control-sm bg-black-20 border-white-10 text-white ${errors.schedule_interval_hours ? "is-invalid" : ""}`}
                        aria-invalid={Boolean(errors.schedule_interval_hours) || undefined}
                        aria-describedby={["search-schedule-help-text", errors.schedule_interval_hours && "search-schedule-error"].filter(Boolean).join(" ")}
                    />
                    <div className="search-presets" aria-label={t("searchForm.intervalPresets")}>
                        {SCHEDULE_PRESETS.map(hours => (
                            <button key={hours} type="button" onClick={() => setProfile(prev => ({ ...prev, schedule_interval_hours: hours }))} className={`search-preset ${profile.schedule_interval_hours == hours ? "is-active" : ""}`}>
                                {hours.toLocaleString(locale)} h
                            </button>
                        ))}
                    </div>
                    <p id="search-schedule-help-text" className="search-field__help">{t("searchForm.intervalHelp")}</p>
                    {errors.schedule_interval_hours && <p id="search-schedule-error" className="field-error" role="alert">{errors.schedule_interval_hours}</p>}
                </div>
            )}

            <div className="search-field">
                <label htmlFor="search-name" className="search-field__label">{t("searchForm.searchTitle")}</label>
                <input
                    id="search-name"
                    type="text"
                    name="name"
                    value={profile.name}
                    onChange={handleChange}
                    placeholder={t("searchForm.searchTitlePlaceholder")}
                    className={`form-control form-control-sm bg-black-20 border-white-10 text-white ${nameIsDuplicate || errors.name ? "is-invalid" : ""}`}
                    aria-invalid={Boolean(nameIsDuplicate || errors.name) || undefined}
                    aria-describedby={nameIsDuplicate || errors.name ? "search-name-error" : "search-name-help"}
                />
                {nameIsDuplicate || errors.name ? (
                    <p id="search-name-error" className="field-error" role="alert">{errors.name || t("searchForm.nameExists")}</p>
                ) : (
                    <p id="search-name-help" className="search-field__help">{t("searchForm.autoName")}</p>
                )}
            </div>

            <div className="search-query-controls">
                <p className="search-section-label">{t("searchForm.queryGeneration")}</p>
                <div className="search-field">
                    <label htmlFor="search-max-queries" className="search-field__label">{t("searchForm.maxQueries")}</label>
                    <input id="search-max-queries" type="number" name="max_queries" value={profile.max_queries} onChange={handleChange} placeholder={t("searchForm.noLimit")} min="0" className="form-control form-control-sm bg-black-20 border-white-10 text-white" />
                </div>
                <div className="search-advanced-grid search-advanced-grid--2">
                    <div className="search-field">
                        <label htmlFor="search-occupation-queries" className="search-field__label">{t("searchForm.occupations")}</label>
                        <input id="search-occupation-queries" type="number" name="max_occupation_queries" value={profile.max_occupation_queries} onChange={handleChange} placeholder={t("searchForm.aiDecides")} min="0" className="form-control form-control-sm bg-black-20 border-white-10 text-white" />
                    </div>
                    <div className="search-field">
                        <label htmlFor="search-keyword-queries" className="search-field__label">{t("searchForm.keywords")}</label>
                        <input id="search-keyword-queries" type="number" name="max_keyword_queries" value={profile.max_keyword_queries} onChange={handleChange} placeholder={t("searchForm.aiDecides")} min="0" className="form-control form-control-sm bg-black-20 border-white-10 text-white" />
                    </div>
                </div>
                <p className="search-field__help">{t("searchForm.queryHelp")}</p>
            </div>

            {isRerun && (
                <div className="search-rerun-options">
                    <p className="search-section-label">{t("searchForm.rerunOptions")}</p>
                    <div className="search-advanced-grid search-advanced-grid--2">
                        <button type="button" aria-pressed={profile.force_regenerate_cv_summary} onClick={() => setProfile(prev => ({ ...prev, force_regenerate_cv_summary: !prev.force_regenerate_cv_summary }))} className={`button button--secondary button--small ${profile.force_regenerate_cv_summary ? "is-active" : ""}`}>
                            <i className="bi bi-arrow-clockwise" aria-hidden="true" />{t("searchForm.refreshSummary")}
                        </button>
                        <button type="button" aria-pressed={profile.force_regenerate_queries} onClick={() => setProfile(prev => ({ ...prev, force_regenerate_queries: !prev.force_regenerate_queries }))} className={`button button--secondary button--small ${profile.force_regenerate_queries ? "is-active" : ""}`}>
                            <i className="bi bi-arrow-clockwise" aria-hidden="true" />{t("searchForm.refreshQueries")}
                        </button>
                    </div>
                    <p className="search-field__help">{t("searchForm.cacheHelp")}</p>
                </div>
            )}
        </section>
    );
}
