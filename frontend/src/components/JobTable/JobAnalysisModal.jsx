import React from "react";
import { createPortal } from "react-dom";
import { ScoreBadge } from "./Badges";

export function JobAnalysisModal({ job, onClose }) {
    if (!job) return null;

    return createPortal(
        <div
            className="position-fixed top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center animate-fade-in"
            style={{ zIndex: 9999, backgroundColor: "rgba(0,0,0,0.85)", backdropFilter: "blur(8px)" }}
            onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
        >
            <div
                className="glass-panel p-4 m-3 animate-slide-up shadow-2xl"
                role="dialog"
                aria-modal="true"
                aria-label="AI Match Analysis"
                style={{ maxWidth: "700px", width: "95%", maxHeight: "85vh", overflowY: "auto", border: "1px solid rgba(255,255,255,0.1)" }}
            >
                <div className="d-flex justify-content-between align-items-center mb-4 border-bottom border-white-10 pb-3">
                    <div>
                        <h5 className="mb-1 text-white d-flex align-items-center gap-2">
                            <i className="bi bi-robot text-info"></i>
                            AI Match Analysis
                        </h5>
                        <div className="x-small text-secondary fw-bold text-uppercase tracking-wider">
                            {job.title} <span className="mx-1 text-muted">•</span> {job.company}
                        </div>
                    </div>
                    <button
                        className="btn btn-link text-secondary p-0 hover-text-white transition-all"
                        aria-label="Close analysis modal"
                        onClick={onClose}
                    >
                        <i className="bi bi-x-lg fs-5"></i>
                    </button>
                </div>
                <div
                    className="text-secondary section-text"
                    style={{ lineHeight: "1.7", whiteSpace: "pre-wrap", fontSize: "0.95rem" }}
                >
                    {job.affinity_analysis}
                </div>
                <div className="mt-5 pt-3 border-top border-white-10 d-flex justify-content-between align-items-center">
                    <ScoreBadge score={Math.round(job.affinity_score)} />
                    <button className="btn btn-secondary px-5 rounded-pill fw-bold" onClick={onClose}>
                        Close
                    </button>
                </div>
            </div>
        </div>,
        document.body
    );
}
