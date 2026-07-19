import React from "react";
import { useI18n } from "../../i18n/useI18n";

export function ProgressBar({ state, isDone, isError, isRunning, progressPct, analyzingText, current_query }) {
    const { t } = useI18n();
    if (state === "pending") return null;

    return (
        <div className="mb-4">
            {isRunning && (
                <div className="mb-2 text-center animate-slide-up">
                    <span className="badge bg-primary-10 text-primary border border-primary-20 rounded-pill fw-normal px-3 py-1 font-monospace small">
                        <i className="bi bi-crosshair me-2"></i>
                        {state === "analyzing" ? analyzingText : (current_query ? t("searchProgress.currentTarget", { query: current_query }) : t("searchProgress.acquiringStrategy"))}
                    </span>
                </div>
            )}
            <div className="d-flex justify-content-between text-secondary x-small fw-bold text-uppercase tracking-wider mb-2">
                <span>{t("searchProgress.progress")}</span>
                <span className="text-white">{isDone ? '100%' : `${progressPct}%`}</span>
            </div>
            <div className="progress bg-black-50 border border-white-5" style={{ height: "8px", borderRadius: "8px" }}>
                <div
                    className={`progress-bar ${isDone ? 'bg-success shadow-glow' : isError ? 'bg-danger' : 'bg-primary shadow-glow progress-bar-striped progress-bar-animated'}`}
                    style={{ width: `${isDone || isError ? 100 : progressPct}%`, borderRadius: "8px", transition: "width 0.5s cubic-bezier(0.4, 0, 0.2, 1)" }}
                />
            </div>
        </div>
    );
}
