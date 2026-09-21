import React from "react";
import { useI18n } from "../../i18n/useI18n";
import { canCancel, canReview } from "./agentWorkModel";

export function AgentWorkCard({ work, onSelect, onCancel }) {
    const { t, language } = useI18n();
    const locale = language === "it" ? "it-IT" : "en-GB";

    const stateClass = `agent-work-state--${work.state}`;
    const kindLabel = t(`agentWork.kind.${work.work_kind}`);
    const stateLabel = t(`agentWork.state.${work.state}`);
    const createdDate = work.created_at ? new Date(work.created_at).toLocaleString(locale) : "—";
    const expiresDate = work.expires_at ? new Date(work.expires_at).toLocaleString(locale) : "—";

    return (
        <article
            className={`agent-work-card ${work.state === "returned" ? "is-review-ready" : ""}`}
            aria-labelledby={`work-title-${work.id}`}
        >
            <div className="agent-work-card__header">
                <div className="agent-work-card__meta">
                    <span className="agent-work-kind-badge">
                        <i
                            className={`bi ${work.work_kind === "discover" ? "bi-search" : work.work_kind === "analyze" ? "bi-cpu" : "bi-file-earmark-text"}`}
                            aria-hidden="true"
                        />
                        {kindLabel}
                    </span>
                    <span className={`agent-work-state-badge ${stateClass}`} role="status">
                        {stateLabel}
                    </span>
                    <span className="agent-work-revision" title={t("agentWork.revision")}>
                        {t("agentWork.revisionNumber", { revision: work.revision })}
                    </span>
                </div>
                <time className="agent-work-date" dateTime={work.created_at}>
                    {createdDate}
                </time>
            </div>

            <div className="agent-work-card__body">
                <h3 id={`work-title-${work.id}`} className="agent-work-card__title">
                    {work.instruction ? work.instruction.slice(0, 140) + (work.instruction.length > 140 ? "…" : "") : t("agentWork.noInstructions")}
                </h3>
                <div className="agent-work-card__details">
                    <span>
                        <i className="bi bi-clock-history me-1" aria-hidden="true" />
                        {t("agentWork.expires")}: {expiresDate}
                    </span>
                    {work.target_job_id && (
                        <span>
                            <i className="bi bi-briefcase me-1" aria-hidden="true" />
                            {t("agentWork.targetJobNumber", { id: work.target_job_id })}
                        </span>
                    )}
                </div>
            </div>

            <div className="agent-work-card__actions">
                {canReview(work) ? (
                    <button
                        type="button"
                        className="button button--primary button--small"
                        onClick={() => onSelect(work)}
                    >
                        <i className="bi bi-check2-circle" aria-hidden="true" />
                        {t("agentWork.reviewProposal")}
                    </button>
                ) : (
                    <button
                        type="button"
                        className="button button--secondary button--small"
                        onClick={() => onSelect(work)}
                    >
                        <i className="bi bi-eye" aria-hidden="true" />
                        {t("agentWork.viewDetails")}
                    </button>
                )}

                {canCancel(work) && onCancel && (
                    <button
                        type="button"
                        className="button button--ghost button--small text-danger"
                        onClick={() => onCancel(work)}
                        aria-label={t("agentWork.cancelRequest")}
                    >
                        <i className="bi bi-x-circle" aria-hidden="true" />
                        {t("agentWork.cancel")}
                    </button>
                )}
            </div>
        </article>
    );
}
