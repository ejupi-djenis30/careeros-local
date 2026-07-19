import React, { memo } from 'react';
import { useI18n } from '../i18n/useI18n';

export const HistoryCard = memo(function HistoryCard({ profile, onStartSearch, onStartSearchWithOptions, onUseAsTemplate, onSaveAsSchedule, isLoading, isDisabled }) {
    const { language, t } = useI18n();
    const locale = language === "it" ? "it-IT" : "en-GB";
    const displayName = (profile.name && profile.name.trim()) || t("historyCard.untitled");
    const advPrefs = profile.advanced_preferences || {};
    const languages = advPrefs.preferred_languages || profile.preferred_languages || [];
    const remoteOnly = advPrefs.remote_only || profile.remote_only;
    const salaryMin = advPrefs.salary_min_chf || profile.salary_min_chf;
    const isActionDisabled = isDisabled || isLoading;
    const postedDays = profile.posted_within_days || 30;
    const scheduleHours = profile.schedule_interval_hours ?? 24;
    const contractLabels = {
        permanent: t("searchForm.permanent"),
        temporary: t("searchForm.temporary"),
    };

    return (
        <div className="glass-panel p-3 px-md-4 py-md-3 hover-bg-white-5 transition-colors group">
            {/* Top row: Icon + Title + Actions */}
            <div className="d-flex align-items-center gap-3 mb-2">
                {/* Icon */}
                <div className="flex-shrink-0">
                    <div className={`rounded-circle d-flex align-items-center justify-content-center text-white shadow-sm border border-white-10 ${profile.schedule_enabled ? 'bg-success' : 'bg-primary'}`} style={{ width: 42, height: 42 }}>
                        <i className={`bi ${profile.schedule_enabled ? 'bi-robot' : 'bi-search'} fs-5`}></i>
                    </div>
                </div>

                {/* Content */}
                <div className="flex-grow-1 min-w-0">
                    {/* Title */}
                    <h6 className="mb-0 fw-bold text-white text-truncate lh-sm" title={displayName}>{displayName}</h6>
                </div>

                {/* Actions */}
                <div className="flex-shrink-0">
                    <div className="d-flex align-items-center gap-2 opacity-75 group-hover-opacity-100 transition-opacity flex-wrap justify-content-end">
                        <button
                            className="btn btn-sm btn-primary px-3 rounded-pill fw-medium shadow-glow d-flex align-items-center justify-content-center"
                            onClick={() => onStartSearch?.(profile)}
                            disabled={isActionDisabled}
                            title={t("historyCard.rerun")}
                        >
                            {isLoading
                                ? <><span className="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> {t("historyCard.running")}</>
                                : <><i className="bi bi-play-fill me-1"></i> {t("historyCard.run")}</>
                            }
                        </button>

                        <button
                            className="btn btn-sm btn-icon btn-secondary rounded-circle d-flex align-items-center justify-content-center"
                            onClick={() => onStartSearchWithOptions?.(profile, { force_regenerate_queries: true })}
                            disabled={isActionDisabled}
                            title={t("historyCard.freshQueries")}
                            aria-label={t("historyCard.freshQueries")}
                        >
                            <i className="bi bi-diagram-3"></i>
                        </button>

                        <button
                            className="btn btn-sm btn-icon btn-secondary rounded-circle d-flex align-items-center justify-content-center"
                            onClick={() => onStartSearchWithOptions?.(profile, { force_regenerate_cv_summary: true })}
                            disabled={isActionDisabled}
                            title={t("historyCard.freshSummary")}
                            aria-label={t("historyCard.freshSummary")}
                        >
                            <i className="bi bi-file-earmark-arrow-up"></i>
                        </button>

                        <button
                            className="btn btn-sm btn-icon btn-warning text-dark rounded-circle d-flex align-items-center justify-content-center"
                            onClick={() => onStartSearchWithOptions?.(profile, { force_regenerate_cv_summary: true, force_regenerate_queries: true })}
                            disabled={isActionDisabled}
                            title={t("historyCard.fullRefresh")}
                            aria-label={t("historyCard.fullRefreshLabel")}
                        >
                            <i className="bi bi-arrow-repeat"></i>
                        </button>

                        <button
                            className="btn btn-sm btn-icon btn-secondary rounded-circle d-flex align-items-center justify-content-center"
                            onClick={() => onUseAsTemplate?.(profile)}
                            disabled={isActionDisabled}
                            title={t("historyCard.useTemplate")}
                        >
                            <i className="bi bi-copy"></i>
                        </button>

                        {!profile.schedule_enabled && (
                            <button
                                className="btn btn-sm btn-icon btn-secondary rounded-circle d-flex align-items-center justify-content-center"
                                onClick={() => onSaveAsSchedule?.(profile)}
                                disabled={isActionDisabled}
                                title={t("historyCard.addSchedule")}
                            >
                                <i className="bi bi-clock"></i>
                            </button>
                        )}
                    </div>
                </div>
            </div>

            <hr className="border-white-10 my-3 opacity-50" />

            {/* Search parameters row */}
            <div className="d-flex flex-wrap column-gap-3 row-gap-1 small text-white-50 lh-sm mb-2">
                <span className="d-flex align-items-center" title={t("historyCard.location")}>
                    <i className="bi bi-geo-alt me-1 text-primary"></i>
                    {profile.location_filter || t("historyCard.anyLocation")}
                </span>
                <span className="d-flex align-items-center" title={t("historyCard.timeRange")}>
                    <i className="bi bi-calendar me-1 text-primary"></i>
                    {t(postedDays === 1 ? "historyCard.lastDay" : "historyCard.lastDays", { count: postedDays })}
                </span>
                {profile.workload_filter && (
                    <span className="d-flex align-items-center" title={t("historyCard.workload")}>
                        <i className="bi bi-briefcase me-1 text-primary"></i>
                        {profile.workload_filter}%
                    </span>
                )}
                {profile.max_distance && (
                    <span className="d-flex align-items-center" title={t("historyCard.maxDistance")}>
                        <i className="bi bi-signpost-2 me-1 text-primary"></i>
                        {profile.max_distance}km
                    </span>
                )}
                {profile.contract_type && profile.contract_type !== "any" && (
                    <span className="d-flex align-items-center" title={t("historyCard.contractType")}>
                        <i className="bi bi-file-text me-1 text-primary"></i>
                        {contractLabels[profile.contract_type] || profile.contract_type}
                    </span>
                )}
                {languages.length > 0 && (
                    <span className="d-flex align-items-center gap-1" title={t("historyCard.preferredLanguages")}>
                        <i className="bi bi-translate me-1 text-primary"></i>
                        {languages.map(l => l.toUpperCase()).join(", ")}
                    </span>
                )}
                {remoteOnly && (
                    <span className="d-flex align-items-center text-info" title={t("historyCard.remoteOnly")}>
                        <i className="bi bi-house me-1"></i>
                        {t("historyCard.remote")}
                    </span>
                )}
                {salaryMin && (
                    <span className="d-flex align-items-center" title={t("historyCard.minimumSalary")}>
                        <i className="bi bi-cash me-1 text-primary"></i>
                        CHF {Number(salaryMin).toLocaleString(locale)}+
                    </span>
                )}
                {profile.schedule_enabled && (
                    <span className="text-success fw-medium d-flex align-items-center">
                        <i className="bi bi-check-circle-fill me-1"></i>
                        {t(scheduleHours === 1 ? "historyCard.autoEveryHour" : "historyCard.autoEvery", { hours: scheduleHours })}
                    </span>
                )}
            </div>

            {/* Role description (multi-line, word-wrap) */}
            {profile.role_description && (
                <div
                    className="text-secondary x-small lh-base text-truncate-2"
                    title={profile.role_description}
                >
                    {profile.role_description}
                </div>
            )}
        </div>
    );
});
