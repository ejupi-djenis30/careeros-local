import React from "react";
import { useI18n } from "../../i18n/useI18n";

const LANGUAGES = [
    { code: "en", label: "EN" },
    { code: "de", label: "DE" },
    { code: "fr", label: "FR" },
    { code: "it", label: "IT" },
];
const POSTED_PRESETS = [1, 3, 7, 14, 30];
const DISTANCE_PRESETS = [25, 50, 100, 250];

export function SearchFormParameters({ profile, handleChange, setProfile, errors = {} }) {
    const { language, t } = useI18n();
    const locale = language === "it" ? "it-IT" : "en-GB";
    const formatNumber = (value) => value === "" || value == null
        ? ""
        : Number(value).toLocaleString(locale);
    const toggleLanguage = (code) => {
        setProfile(prev => {
            const current = prev.preferred_languages || [];
            const next = current.includes(code)
                ? current.filter(v => v !== code)
                : [...current, code];
            return { ...prev, preferred_languages: next };
        });
    };

    return (
        <section className="search-advanced-panel" aria-labelledby="search-preferences-title">
            <div className="search-advanced-panel__heading">
                <span className="search-advanced-panel__icon" aria-hidden="true"><i className="bi bi-sliders" /></span>
                <div>
                    <p className="search-section-label">{t("searchForm.preferences.eyebrow")}</p>
                    <h4 id="search-preferences-title">{t("searchForm.preferences.title")}</h4>
                </div>
            </div>

            <div className="search-advanced-grid search-advanced-grid--2">
                <div className="search-field">
                    <label htmlFor="search-workload" className="search-field__label">{t("searchForm.workload")}</label>
                    <select id="search-workload" name="workload_filter" value={profile.workload_filter} onChange={handleChange} className="form-select form-select-sm bg-black-20 border-white-10 text-white">
                        <option value="80-100">80-100%</option>
                        <option value="100">100% ({t("searchForm.fullTime")})</option>
                        <option value="50-100">50-100%</option>
                        <option value="0-100">{t("filter.any")}</option>
                    </select>
                </div>
                <div className="search-field">
                    <label htmlFor="search-contract" className="search-field__label">{t("searchForm.contract")}</label>
                    <select id="search-contract" name="contract_type" value={profile.contract_type || "any"} onChange={handleChange} className="form-select form-select-sm bg-black-20 border-white-10 text-white">
                        <option value="any">{t("filter.any")}</option>
                        <option value="permanent">{t("searchForm.permanent")}</option>
                        <option value="temporary">{t("searchForm.temporary")}</option>
                    </select>
                </div>
            </div>

            <div className="search-field">
                <label htmlFor="search-posted-days" className="search-field__label">{t("searchForm.posted")}</label>
                <input
                    id="search-posted-days"
                    type="number"
                    name="posted_within_days"
                    value={profile.posted_within_days}
                    onChange={handleChange}
                    min="1"
                    step="1"
                    className={`form-control form-control-sm bg-black-20 border-white-10 text-white ${errors.posted_within_days ? "is-invalid" : ""}`}
                    aria-invalid={Boolean(errors.posted_within_days) || undefined}
                    aria-describedby={errors.posted_within_days ? "search-posted-days-error" : undefined}
                />
                <div className="search-presets" aria-label={t("searchForm.postedPresets")}>
                    {POSTED_PRESETS.map((days) => (
                        <button key={days} type="button" onClick={() => setProfile(prev => ({ ...prev, posted_within_days: days }))} className={`search-preset ${profile.posted_within_days == days ? "is-active" : ""}`}>
                            {formatNumber(days)}{t("searchForm.dayShort")}
                        </button>
                    ))}
                </div>
                {errors.posted_within_days && <p id="search-posted-days-error" className="field-error" role="alert">{errors.posted_within_days}</p>}
            </div>

            <div className={`search-distance ${profile.remote_only ? "is-disabled" : ""}`}>
                <div className="search-distance__heading">
                    <label htmlFor="search-max-distance" className="search-field__label">{t("searchForm.maxDistance")}</label>
                    <strong>{profile.remote_only ? t("searchForm.distanceRemote") : `${formatNumber(profile.max_distance)} km`}</strong>
                </div>
                <input
                    id="search-max-distance"
                    type="number"
                    name="max_distance"
                    min="0"
                    step="1"
                    value={profile.max_distance}
                    onChange={handleChange}
                    disabled={profile.remote_only}
                    className={`form-control form-control-sm bg-black-20 border-white-10 text-white ${errors.max_distance ? "is-invalid" : ""}`}
                    aria-invalid={Boolean(errors.max_distance) || undefined}
                    aria-describedby={["search-distance-help", errors.max_distance && "search-distance-error"].filter(Boolean).join(" ")}
                />
                <div className="search-presets" aria-label={t("searchForm.distancePresets")}>
                    {DISTANCE_PRESETS.map((distance) => (
                        <button key={distance} type="button" disabled={profile.remote_only} onClick={() => setProfile(prev => ({ ...prev, max_distance: distance }))} className={`search-preset ${profile.max_distance == distance && !profile.remote_only ? "is-active" : ""}`}>
                            {formatNumber(distance)} km
                        </button>
                    ))}
                </div>
                <p id="search-distance-help" className="search-field__help">{profile.remote_only ? t("searchForm.distanceRemoteHelp") : t("searchForm.distanceHelp")}</p>
                {errors.max_distance && <p id="search-distance-error" className="field-error" role="alert">{errors.max_distance}</p>}
            </div>

            <div className="search-field">
                <span className="search-field__label" id="search-languages-label">{t("searchForm.jobLanguage")}</span>
                <div className="search-chip-list" aria-labelledby="search-languages-label">
                    {LANGUAGES.map(({ code, label }) => {
                        const active = (profile.preferred_languages || []).includes(code);
                        return (
                            <button key={code} type="button" aria-pressed={active} onClick={() => toggleLanguage(code)} className={`search-chip ${active ? "is-active" : ""}`}>
                                {label}
                            </button>
                        );
                    })}
                </div>
                <p className="search-field__help">{t("searchForm.languagesHelp")}</p>
            </div>

            <div className="search-field">
                <label htmlFor="search-min-salary" className="search-field__label">{t("searchForm.minSalary")}</label>
                <input id="search-min-salary" type="number" name="salary_min_chf" value={profile.salary_min_chf || ""} onChange={handleChange} placeholder={t("searchForm.noMinimum")} min="0" step="1000" className="form-control form-control-sm bg-black-20 border-white-10 text-white" />
            </div>
        </section>
    );
}
