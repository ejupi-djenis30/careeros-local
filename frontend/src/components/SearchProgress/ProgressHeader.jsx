import React from "react";
import { useI18n } from "../../i18n/useI18n";

export function ProgressHeader({
    isDone,
    isError,
    isRunning,
    state,
    searches_completed,
    active_search_indices,
    total_searches,
    handleStop,
    onClear
}) {
    const { language, t } = useI18n();
    const locale = language === "it" ? "it-IT" : "en-GB";
    const formatCount = (value) => Number(value || 0).toLocaleString(locale);
    const completedCount = searches_completed || 0;
    const activeCount = (active_search_indices || []).length;
    const searchSubtitle = activeCount > 0
        ? t(activeCount === 1 ? "searchProgress.executingOne" : "searchProgress.executingMany", { active: formatCount(activeCount), completed: formatCount(completedCount), total: formatCount(total_searches) })
        : t("searchProgress.processed", { completed: formatCount(completedCount), total: formatCount(total_searches) });

    return (
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-4 mb-4">
            <div className="d-flex align-items-center gap-4">
                <div className={`rounded-circle d-flex align-items-center justify-content-center text-white shadow-lg border border-white-10 ${isDone ? 'bg-success' : isError ? 'bg-danger' : 'bg-primary'}`} style={{ width: 64, height: 64 }}>
                    {isRunning ? <span className="spinner-border spinner-border-sm" style={{ width: '2rem', height: '2rem' }}></span>
                        : isDone ? <i className="bi bi-check-lg fs-2"></i>
                            : <i className="bi bi-exclamation-triangle fs-2"></i>}
                </div>
                <div>
                    <h2 className="mb-0 fw-bold text-white tracking-tight">
                        {isDone ? t("searchProgress.complete") : isError ? (state === "stopped" ? t("searchProgress.aborted") : t("searchProgress.failed")) : t("searchProgress.active")}
                    </h2>
                    <p className="text-white-50 mb-0 font-monospace small">
                        {state === "generating" && t("searchProgress.generating")}
                        {state === "searching" && searchSubtitle}
                        {state === "analyzing" && t("searchProgress.analyzingData")}
                        {state === "done" && t("searchProgress.doneCopy")}
                    </p>
                </div>
            </div>

            <div className="d-flex gap-3">
                {isRunning && (
                    <button className="btn btn-outline-danger border-white-10 bg-black-20 rounded-pill px-4 hover-bg-danger hover-text-white transition-all" onClick={handleStop}>
                        <i className="bi bi-stop-circle me-2"></i>{t("searchProgress.abort")}
                    </button>
                )}
                {(isDone || isError) && (
                    <button className="btn btn-secondary rounded-pill px-5 shadow-glow" onClick={onClear}>
                        {t("common.close")}
                    </button>
                )}
            </div>
        </div>
    );
}
