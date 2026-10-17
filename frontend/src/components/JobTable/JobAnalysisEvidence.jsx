import { AnalysisClaims, AnalysisGates, ExternalScoreBreakdown } from "./JobAnalysisSections";

export function JobAnalysisEvidence({ job, structured, citations, gates, isExternalAgent, scores, claims, descriptionId, t }) {
    return (
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
            {scores && <ExternalScoreBreakdown scores={scores} t={t} />}
            {gates.length > 0 && <AnalysisGates gates={gates} t={t} />}
            {claims.length > 0 && <AnalysisClaims claims={claims} t={t} />}
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
    );
}
