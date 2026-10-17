const EXTERNAL_SCORE_DIMENSIONS = [
    "role",
    "requirements",
    "language",
    "location",
    "contract",
    "freshness",
];

export function ExternalScoreBreakdown({ scores, t }) {
    return (
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
    );
}

export function AnalysisGates({ gates, t }) {
    return (
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
    );
}

export function AnalysisClaims({ claims, t }) {
    return (
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
    );
}
