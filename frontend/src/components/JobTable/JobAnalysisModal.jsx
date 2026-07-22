import React, { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { ScoreBadge } from "./Badges";
import { useI18n } from "../../i18n/useI18n";

const FOCUSABLE = [
    "button:not([disabled])",
    "[href]",
    "input:not([disabled])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "[tabindex]:not([tabindex='-1'])",
].join(",");

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
    const isValidated = job.analysis_verified === true;

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
                                <strong>{t("jobs.analysis.validated")}</strong>
                            </div>
                            <code>{job.analysis_model_id}</code>
                            <code>{t("jobs.analysis.contract", { version: job.analysis_contract_version })}</code>
                        </div>
                        {structured.recommendation && (
                            <p className="match-evidence__recommendation">
                                <span>{t("jobs.analysis.recommendation")}</span>
                                <strong>{t(`jobs.analysis.recommendation.${structured.recommendation}`)}</strong>
                            </p>
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
                <div className="mt-5 pt-3 border-top border-white-10 d-flex justify-content-between align-items-center">
                    {isValidated && Number.isFinite(Number(job.affinity_score))
                        ? <ScoreBadge score={Math.round(Number(job.affinity_score))} />
                        : <span />}
                    <button type="button" className="btn btn-secondary px-5 rounded-pill fw-bold" onClick={() => closeHandlerRef.current?.()}>
                        {t("common.close")}
                    </button>
                </div>
            </div>
        </div>,
        document.body
    );
}
