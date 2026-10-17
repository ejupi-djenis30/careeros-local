import React, { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { ScoreBadge } from "./Badges";
import { InternalLink } from "../InternalLink";
import { useI18n } from "../../i18n/useI18n";
import { useModalIsolation } from "../modals/useModalIsolation";
import { JobAnalysisEvidence } from "./JobAnalysisEvidence";

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

    useModalIsolation({
        isOpen: open,
        dialogRef,
        initialFocusRef: closeRef,
        onRequestClose: onClose,
    });

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
                    <JobAnalysisEvidence
                        job={job} structured={structured} citations={citations} gates={gates}
                        isExternalAgent={isExternalAgent} scores={scores} claims={claims}
                        descriptionId={descriptionId} t={t}
                    />
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
