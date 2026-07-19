import React from "react";
import { useI18n } from "../../i18n/useI18n";

const SCHEDULE_PRESETS = [6, 12, 24];

export function SearchFormAdvanced({ profile, handleChange, setProfile, existingNames = [] }) {
    const { language, t } = useI18n();
    const locale = language === "it" ? "it-IT" : "en-GB";
    // A profile is considered "existing" (re-run) when it has a non-null id
    const isRerun = profile.id != null;
    const nameIsDuplicate = profile.name.trim() && existingNames.includes(profile.name.trim().toLowerCase());

    return (
        <div className="col-xl-3 col-lg-12 d-flex flex-column gap-3">
            <div className="p-3 bg-white-5 rounded-3 border border-white-5">
                <div className="form-check form-switch d-flex align-items-center justify-content-between ps-0 mb-3">
                    <div>
                        <label className="form-check-label fw-bold text-white small mb-0" htmlFor="scheduleSwitch">{t("searchForm.automatic")}</label>
                        <div className="x-small text-secondary opacity-75">{t("searchForm.automaticCopy")}</div>
                    </div>
                    <input
                        className="form-check-input ms-2"
                        type="checkbox"
                        id="scheduleSwitch"
                        checked={profile.schedule_enabled}
                        onChange={(e) => setProfile(prev => ({ ...prev, schedule_enabled: e.target.checked }))}
                        style={{cursor: 'pointer'}}
                    />
                </div>

                {profile.schedule_enabled && (
                    <div className="border-top border-white-10 pt-3 opacity-animation">
                        <div className="d-flex align-items-center justify-content-between gap-3 mb-2">
                            <span className="x-small text-secondary fw-bold text-uppercase">{t("searchForm.intervalHours")}</span>
                            <input
                                type="number"
                                name="schedule_interval_hours"
                                value={profile.schedule_interval_hours}
                                onChange={handleChange}
                                min="1"
                                step="1"
                                className="form-control form-control-sm bg-black-20 border-white-10 text-white"
                                style={{ maxWidth: 120 }}
                            />
                        </div>
                        <div className="btn-group btn-group-sm" role="group">
                            {SCHEDULE_PRESETS.map(h => (
                                <button
                                    key={h}
                                    type="button"
                                    onClick={() => setProfile(prev => ({ ...prev, schedule_interval_hours: h }))}
                                    className={"btn " + (profile.schedule_interval_hours == h ? 'btn-light text-dark fw-bold' : 'btn-outline-secondary')}
                                >
                                    {h.toLocaleString(locale)} h
                                </button>
                            ))}
                        </div>
                        <div className="x-small text-secondary mt-2 opacity-60">
                            {t("searchForm.intervalHelp")}
                        </div>
                    </div>
                )}
            </div>

            <div>
                <label className="form-label text-white small fw-bold text-uppercase x-small mb-2">{t("searchForm.searchTitle")}</label>
                <input
                    type="text"
                    name="name"
                    value={profile.name}
                    onChange={handleChange}
                    placeholder={t("searchForm.searchTitlePlaceholder")}
                    className={"form-control form-control-sm bg-black-20 border-white-10 text-white " + (nameIsDuplicate ? 'border-danger' : '')}
                />
                {nameIsDuplicate ? (
                    <div className="x-small text-danger mt-1">{t("searchForm.nameExists")}</div>
                ) : (
                    <div className="x-small text-secondary mt-1 opacity-75">{t("searchForm.autoName")}</div>
                )}
            </div>

            {/* Query Controls */}
            <div className="p-3 bg-white-5 rounded-3 border border-white-5">
                <div className="x-small text-secondary fw-bold text-uppercase mb-3">{t("searchForm.queryGeneration")}</div>

                <div className="row g-2 mb-2">
                    <div className="col-12">
                        <label className="form-label text-white x-small fw-semibold mb-1">{t("searchForm.maxQueries")}</label>
                        <input
                            type="number"
                            name="max_queries"
                            value={profile.max_queries}
                            onChange={handleChange}
                            placeholder={t("searchForm.noLimit")}
                            min="1"
                            className="form-control form-control-sm bg-black-20 border-white-10 text-white"
                        />
                    </div>
                </div>

                <div className="row g-2">
                    <div className="col-6">
                        <label className="form-label text-secondary x-small mb-1">
                            <i className="bi bi-briefcase-fill me-1 opacity-50"></i>{t("searchForm.occupations")}
                        </label>
                        <input
                            type="number"
                            name="max_occupation_queries"
                            value={profile.max_occupation_queries}
                            onChange={handleChange}
                            placeholder={t("searchForm.aiDecides")}
                            min="0"
                            className="form-control form-control-sm bg-black-20 border-white-10 text-white"
                        />
                    </div>
                    <div className="col-6">
                        <label className="form-label text-secondary x-small mb-1">
                            <i className="bi bi-key-fill me-1 opacity-50"></i>{t("searchForm.keywords")}
                        </label>
                        <input
                            type="number"
                            name="max_keyword_queries"
                            value={profile.max_keyword_queries}
                            onChange={handleChange}
                            placeholder={t("searchForm.aiDecides")}
                            min="0"
                            className="form-control form-control-sm bg-black-20 border-white-10 text-white"
                        />
                    </div>
                </div>
                <div className="x-small text-secondary mt-2 opacity-60">
                    {t("searchForm.queryHelp")}
                </div>
            </div>

            {/* Feature 3: Force Regeneration Buttons (only on re-run) */}
            {isRerun && (
                <div className="p-3 bg-warning bg-opacity-10 rounded-3 border border-warning border-opacity-20">
                    <div className="x-small text-warning fw-bold text-uppercase mb-2">
                        <i className="bi bi-lightning-charge-fill me-1"></i>{t("searchForm.rerunOptions")}
                    </div>
                    <div className="row g-2">
                        <div className="col-12 col-sm-6 col-lg-12 col-xl-6">
                        <button
                            type="button"
                            onClick={() => setProfile(prev => ({ ...prev, force_regenerate_cv_summary: !prev.force_regenerate_cv_summary }))}
                            className={"btn btn-sm w-100 d-flex align-items-center justify-content-center gap-2 " + (profile.force_regenerate_cv_summary ? 'btn-warning text-dark fw-bold' : 'btn-outline-secondary')}
                        >
                            <i className={"bi " + (profile.force_regenerate_cv_summary ? 'bi-check-circle-fill' : 'bi-arrow-clockwise')}></i>
                            {t("searchForm.refreshSummary")}
                        </button>
                        </div>
                        <div className="col-12 col-sm-6 col-lg-12 col-xl-6">
                        <button
                            type="button"
                            onClick={() => setProfile(prev => ({ ...prev, force_regenerate_queries: !prev.force_regenerate_queries }))}
                            className={"btn btn-sm w-100 d-flex align-items-center justify-content-center gap-2 " + (profile.force_regenerate_queries ? 'btn-warning text-dark fw-bold' : 'btn-outline-secondary')}
                        >
                            <i className={"bi " + (profile.force_regenerate_queries ? 'bi-check-circle-fill' : 'bi-arrow-clockwise')}></i>
                            {t("searchForm.refreshQueries")}
                        </button>
                        </div>
                    </div>
                    <div className="x-small text-warning opacity-75 mt-2">
                        {t("searchForm.cacheHelp")}
                    </div>
                </div>
            )}
        </div>
    );
}
