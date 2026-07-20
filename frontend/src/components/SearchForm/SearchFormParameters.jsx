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

export function SearchFormParameters({ profile, handleChange, setProfile }) {
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
        <div className="col-xl-4 col-lg-6 d-flex flex-column gap-4 border-end border-white-5">
            <div className="row g-3">
                <div className="col-6">
                    <label className="form-label text-white small fw-bold text-uppercase x-small mb-2">{t("searchForm.workload")}</label>
                    <select
                        name="workload_filter"
                        value={profile.workload_filter}
                        onChange={handleChange}
                        className="form-select form-select-sm bg-black-20 border-white-10 text-white"
                    >
                        <option value="80-100">80-100%</option>
                        <option value="100">100% ({t("searchForm.fullTime")})</option>
                        <option value="50-100">50-100%</option>
                        <option value="0-100">{t("filter.any")}</option>
                    </select>
                </div>
                <div className="col-6">
                    <label className="form-label text-white small fw-bold text-uppercase x-small mb-2">{t("searchForm.contract")}</label>
                    <select
                        name="contract_type"
                        value={profile.contract_type || "any"}
                        onChange={handleChange}
                        className="form-select form-select-sm bg-black-20 border-white-10 text-white"
                    >
                        <option value="any">{t("filter.any")}</option>
                        <option value="permanent">{t("searchForm.permanent")}</option>
                        <option value="temporary">{t("searchForm.temporary")}</option>
                    </select>
                </div>
            </div>

            <div className="row g-3">
                <div className="col-12">
                    <label className="form-label text-white small fw-bold text-uppercase x-small mb-2">{t("searchForm.posted")}</label>
                    <input
                        type="number"
                        name="posted_within_days"
                        value={profile.posted_within_days}
                        onChange={handleChange}
                        min="1"
                        step="1"
                        className="form-control form-control-sm bg-black-20 border-white-10 text-white"
                    />
                    <div className="d-flex flex-wrap gap-1 mt-2">
                        {POSTED_PRESETS.map((days) => (
                            <button
                                key={days}
                                type="button"
                                onClick={() => setProfile(prev => ({ ...prev, posted_within_days: days }))}
                                className={`btn btn-sm px-2 py-0 rounded-pill ${profile.posted_within_days == days ? "btn-info text-dark fw-bold" : "btn-outline-secondary opacity-75"}`}
                            >
                                {formatNumber(days)}{t("searchForm.dayShort")}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            <div className="p-3 bg-white-5 rounded-3 border border-white-5">
                <div className="d-flex justify-content-between mb-2">
                    <label className="form-label text-white small fw-bold text-uppercase x-small mb-0">{t("searchForm.maxDistance")}</label>
                    <span className="x-small text-info fw-bold">{formatNumber(profile.max_distance)} km</span>
                </div>
                <input
                    type="number"
                    name="max_distance"
                    min="0"
                    step="1"
                    value={profile.max_distance}
                    onChange={handleChange}
                    className="form-control form-control-sm bg-black-20 border-white-10 text-white"
                />
                <div className="d-flex flex-wrap gap-1 mt-2">
                    {DISTANCE_PRESETS.map((distance) => (
                        <button
                            key={distance}
                            type="button"
                            onClick={() => setProfile(prev => ({ ...prev, max_distance: distance }))}
                            className={`btn btn-sm px-2 py-0 rounded-pill ${profile.max_distance == distance ? "btn-info text-dark fw-bold" : "btn-outline-secondary opacity-75"}`}
                        >
                            {formatNumber(distance)} km
                        </button>
                    ))}
                </div>
                <div className="x-small text-secondary opacity-60 mt-2">
                    {t("searchForm.distanceHelp")}
                </div>
            </div>

            {/* Precision Filters */}
            <div className="p-3 bg-white-5 rounded-3 border border-white-5">
                <div className="x-small text-secondary fw-bold text-uppercase mb-3 d-flex align-items-center gap-2">
                    <i className="bi bi-funnel-fill"></i>{t("searchForm.preferenceFilters")}
                </div>

                {/* Job Language chips */}
                <div className="mb-3">
                    <div className="x-small text-white fw-semibold mb-2">{t("searchForm.jobLanguage")}</div>
                    <div className="d-flex flex-wrap gap-1">
                        {LANGUAGES.map(({ code, label }) => {
                            const active = (profile.preferred_languages || []).includes(code);
                            return (
                                <button key={code} type="button"
                                    onClick={() => toggleLanguage(code)}
                                    className={`btn btn-sm px-2 py-0 rounded-pill ${active ? "btn-info text-dark fw-bold" : "btn-outline-secondary opacity-75"}`}
                                    style={{ fontSize: "0.7rem", minWidth: 34 }}
                                >
                                    {label}
                                </button>
                            );
                        })}
                    </div>
                    <div className="x-small text-secondary opacity-60 mt-1">{t("searchForm.languagesHelp")}</div>
                </div>

                {/* Remote toggle + Min Salary */}
                <div className="row g-2 align-items-end">
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
                                {t("searchForm.remoteOnly")}
                            </label>
                        </div>
                    </div>
                    <div className="col-6">
                        <label className="form-label text-secondary x-small mb-1">{t("searchForm.minSalary")}</label>
                        <input
                            type="number"
                            name="salary_min_chf"
                            value={profile.salary_min_chf || ""}
                            onChange={handleChange}
                            placeholder={t("searchForm.noMinimum")}
                            min="0"
                            step="1000"
                            className="form-control form-control-sm bg-black-20 border-white-10 text-white"
                        />
                    </div>
                </div>
                <div className="x-small text-secondary opacity-60 mt-3">
                    {t("searchForm.preferencesHelp")}
                </div>
            </div>
        </div>
    );
}
