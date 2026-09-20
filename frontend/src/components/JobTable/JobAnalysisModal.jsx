import React, { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { ScoreBadge } from "./Badges";
import { InternalLink } from "../InternalLink";
import { useI18n } from "../../i18n/useI18n";

const FOCUSABLE = [
    "button:not([disabled])",
    "[href]",
    "input:not([disabled])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "[tabindex]:not([tabindex='-1'])",
].join(",");

const EXTERNAL_SCORE_DIMENSIONS = [
    "role",
    "requirements",
    "language",
    "location",
    "contract",
    "freshness",
];

export function JobAnalysisModal({ job, onClose }) {
    const { t } = useI18n();
    const titleId = useId();
    const descriptionId = useId();
    const dialogRef = useRef(null);
    const closeRef = useRef(null);
    const closeHandlerRef = useRef(onClose);
    const open = Boolean(job);

    useEffect(() => {
        closeHandlerRef.current = onClose;
    }, [onClose]);

    useEffect(() => {
        if (!open) return undefined;
        const previouslyFocused = document.activeElement;
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        closeRef.current?.focus();

        const handleKeyDown = (event) => {
            if (event.key === "Escape") {
                event.preventDefault();
                closeHandlerRef.current?.();
                return;
            }
            if (event.key !== "Tab") return;

            const focusable = Array.from(dialogRef.current?.querySelectorAll(FOCUSABLE) || []);
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (!first || !last) {
                event.preventDefault();
                dialogRef.current?.focus();
                return;
            }
            if (!dialogRef.current?.contains(document.activeElement)) {
                event.preventDefault();
                (event.shiftKey ? last : first).focus();
            } else if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        };

        document.addEventListener("keydown", handleKeyDown);
        return () => {
            document.removeEventListener("keydown", handleKeyDown);
            document.body.style.overflow = previousOverflow;
            if (previouslyFocused instanceof HTMLElement && document.contains(previouslyFocused)) {
                previouslyFocused.focus();
            }
        };
    }, [open]);

    if (!job) return null;
    const structured = job.analysis_structured || {};
    const citations = Array.isArray(structured.evidence_citations)
        ? structured.evidence_citations
        : [];
    const gates = Array.isArray(structured.gates) ? structured.gates : [];
    const isExternalAgent = job.external_analysis_verified === true
        && job.analysis_provenance === "external_agent_proposal";
    const isValidated = job.analysis_verified === true || isExternalAgent;
    const scores = isExternalAgent && structured.scores && typeof structured.scores === "object"
        ? structured.scores
        : null;
    const claims = isExternalAgent && Array.isArray(structured.claims)
        ? structured.claims
        : [];

    return createPortal(
        <div
            className="position-fixed top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center animate-fade-in custom-modal-backdrop"
            onClick={(e) => { if (e.target === e.currentTarget) closeHandlerRef.current?.(); }}
        >
            <div
                ref={dialogRef}
                className="job-analysis-dialog p-4 m-3 animate-slide-up shadow-2xl custom-modal-content"
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
                aria-describedby={descriptionId}
                tabIndex="-1"
            >
                <div className="d-flex justify-content-between align-items-center mb-4 border-bottom border-white-10 pb-3">
                    <div>
                        <h5 className="mb-1 text-white d-flex align-items-center gap-2" id={titleId}>
                            <i className="bi bi-cpu text-info"></i>
                            {t("jobs.analysis.title")}
                        </h5>
                        <div className="x-small text-secondary fw-bold text-uppercase tracking-wider">
                            {job.title} <span className="mx-1 text-muted">•</span> {job.company}
                        </div>
                    </div>
                    <button
                        ref={closeRef}
                        type="button"
                        className="btn btn-link text-secondary p-0 hover-text-white transition-all"
                        aria-label={t("jobs.analysis.closeLabel")}
                        onClick={() => closeHandlerRef.current?.()}
                    >
                        <i className="bi bi-x-lg fs-5"></i>
                    </button>
                </div>
                {isValidated ? (
                    <div className="match-evidence" data-testid="validated-match-evidence" id={descriptionId}>
                        <p className="match-evidence__narrative">
                            {job.affinity_analysis || t("jobs.analysis.empty")}
                        </p>
                        <div className="match-evidence__provenance">
                            <div>
                                <span>{t("jobs.analysis.provenance")}</span>
                                <strong>
                                    {isExternalAgent
                                        ? t("jobs.analysis.externalAgent")
                                        : t("jobs.analysis.validated")}
                                </strong>
                            </div>
                            <code>{job.analysis_client || job.analysis_model_id}</code>
                            <code>{t("jobs.analysis.contract", { version: job.analysis_contract_version })}</code>
                        </div>
                        {structured.recommendation && (
                            <p className="match-evidence__recommendation">
                                <span>{t("jobs.analysis.recommendation")}</span>
                                <strong>{t(`jobs.analysis.recommendation.${structured.recommendation}`)}</strong>
                            </p>
                        )}
                        {scores && (
                            <section className="my-3" aria-label={t("agentWork.scoreBreakdown")}>
                                <h6 className="text-white-50 text-uppercase x-small fw-bold mb-2">
                                    {t("agentWork.scoreBreakdown")}
                                </h6>
                                <dl className="d-flex flex-column gap-2 mb-0">
                                    {EXTERNAL_SCORE_DIMENSIONS.map((dimension) => {
                                        const score = scores[dimension];
                                        if (!score) return null;
                                        return (
                                            <div key={dimension} className="p-2 rounded bg-white-5 border border-white-10">
                                                <dt className="d-flex justify-content-between gap-2 text-white small">
                                                    <span>{t(`jobs.analysis.dimension.${dimension}`)}</span>
                                                    <strong>{score.score}%</strong>
                                                </dt>
                                                <dd className="x-small text-secondary mb-0">{score.explanation}</dd>
                                            </div>
                                        );
                                    })}
                                </dl>
                            </section>
                        )}
                        {gates.length > 0 && (
                            <div className="match-evidence__gates my-3">
                                <h6 className="text-white-50 text-uppercase x-small fw-bold mb-2">
                                    {t("agentWork.hardGatesTitle")}
                                </h6>
                                <div className="d-flex flex-column gap-2">
                                    {gates.map((gate, index) => {
                                        const status = gate.status;
                                        return (
                                        <div key={gate.dimension || index} className="p-2 rounded bg-white-5 border border-white-10">
                                            <div className="d-flex justify-content-between align-items-center mb-1">
                                                <strong className="text-white small">
                                                    {t(`jobs.analysis.dimension.${gate.dimension}`) || gate.dimension}
                                                </strong>
                                                <span className={`badge ${status === "eligible" ? "bg-success" : status === "reject" ? "bg-danger" : "bg-warning text-dark"}`}>
                                                    {t(`agentWork.gate.${status}`)}
                                                </span>
                                            </div>
                                            {gate.reason && <p className="x-small text-secondary mb-1">{gate.reason}</p>}
                                            {gate.quote_references?.length > 0 && (
                                                <div className="x-small text-muted mb-1">
                                                    <em>“{gate.quote_references[0]}”</em>
                                                </div>
                                            )}
                                            {gate.unknowns?.length > 0 && (
                                                <div className="x-small text-warning">
                                                    <i className="bi bi-question-diamond me-1" aria-hidden="true" />
                                                    {gate.unknowns.join(", ")}
                                                </div>
                                            )}
                                        </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}
                        {claims.length > 0 && (
                            <section className="my-3" aria-labelledby="external-analysis-claims-title">
                                <h6 id="external-analysis-claims-title" className="text-white-50 text-uppercase x-small fw-bold mb-2">
                                    {t("agentWork.analysisClaims")}
                                </h6>
                                <div className="d-flex flex-column gap-2">
                                    {claims.map((claim, index) => (
                                        <article key={`${claim.claim_text}-${index}`} className="p-2 rounded bg-white-5 border border-white-10">
                                            <p className="small text-white mb-1">{claim.claim_text}</p>
                                            {claim.quote_text && <blockquote className="x-small text-secondary mb-1">“{claim.quote_text}”</blockquote>}
                                            {claim.fact_ids?.length > 0 && (
                                                <p className="x-small text-muted mb-0">
                                                    {t("agentWork.citations")}: {claim.fact_ids.join(", ")}
                                                </p>
                                            )}
                                        </article>
                                    ))}
                                </div>
                            </section>
                        )}
                        <div className="match-evidence__citations">
                            {citations.map((citation, index) => (
                                <article key={`${citation.type}-${citation.assessment}-${index}`}>
                                    <header>
                                        <strong>{t(`jobs.analysis.dimension.${citation.type}`)}</strong>
                                        <span>{t(`jobs.analysis.assessment.${citation.assessment}`)}</span>
                                    </header>
                                    <dl>
                                        <div>
                                            <dt>{citation.job_evidence_id}</dt>
                                            <dd>“{citation.job_evidence}”</dd>
                                        </div>
                                        <div>
                                            <dt>{citation.candidate_evidence_id}</dt>
                                            <dd>“{citation.candidate_evidence}”</dd>
                                        </div>
                                    </dl>
                                </article>
                            ))}
                        </div>
                    </div>
                ) : (
                    <p className="match-evidence__unverified" role="status" id={descriptionId}>
                        {t("jobs.analysis.unverified")}
                    </p>
                )}
                <div className="mt-5 pt-3 border-top border-white-10 d-flex justify-content-between align-items-center flex-wrap gap-2">
                    {isValidated && Number.isFinite(Number(job.affinity_score))
                        ? <ScoreBadge score={Math.round(Number(job.affinity_score))} />
                        : <span />}
                    <div className="d-flex gap-2">
                        <InternalLink
                            to={`/agent-work?kind=analyze&job_id=${encodeURIComponent(job.id)}`}
                            className="btn btn-outline-info rounded-pill fw-medium d-inline-flex align-items-center gap-1"
                            onClick={() => closeHandlerRef.current?.()}
                        >
                            <i className="bi bi-robot" aria-hidden="true" />
                            {t("jobs.analysis.analyzeWithAgent")}
                        </InternalLink>
                        <button type="button" className="btn btn-secondary px-5 rounded-pill fw-bold" onClick={() => closeHandlerRef.current?.()}>
                            {t("common.close")}
                        </button>
                    </div>
                </div>
            </div>
        </div>,
        document.body
    );
}
