import React, { useState } from "react";

import { useI18n } from "../../i18n/useI18n";
import { safeExternalUrl } from "../../lib/safeUrl";
import { proposalPayload, proposalSupportsReview } from "./agentWorkModel";

const SCORE_DIMENSIONS = ["role", "requirements", "language", "location", "contract", "freshness"];

function FactCitations({ factIds = [], t }) {
    if (!factIds.length) return null;
    return (
        <div className="fact-citations">
            <small>{t("agentWork.citations")}: </small>
            {factIds.map((id) => <code key={id}>{id}</code>)}
        </div>
    );
}

function CitedTextList({ items = [], t }) {
    if (!items.length) return <p>{t("agentWork.noneProposed")}</p>;
    return (
        <div className="agent-letter-paragraphs">
            {items.map((item, index) => (
                <article key={item.id || index} className="agent-letter-para">
                    <p>{item.text}</p>
                    <FactCitations factIds={item.fact_ids} t={t} />
                </article>
            ))}
        </div>
    );
}

function ScoreView({ scores, t }) {
    if (!scores) return null;
    return (
        <section className="agent-scorecard" aria-label={t("agentWork.scoreBreakdown")}>
            <div className="agent-overall-score">
                <span className="score-number">{scores.overall_score}</span>
                <span className="score-label">{t("agentWork.overallAffinity")}</span>
            </div>
            <div className="agent-dimension-scores">
                {SCORE_DIMENSIONS.map((dimension) => {
                    const value = scores[dimension];
                    if (!value) return null;
                    return (
                        <div key={dimension} className="agent-dimension-item">
                            <div className="agent-dimension-header">
                                <span>{t(`jobs.analysis.dimension.${dimension}`)}</span>
                                <strong>{value.score}%</strong>
                            </div>
                            <div
                                className="agent-score-bar"
                                role="progressbar"
                                aria-label={t(`jobs.analysis.dimension.${dimension}`)}
                                aria-valuenow={value.score}
                                aria-valuemin="0"
                                aria-valuemax="100"
                            >
                                <div
                                    className="agent-score-bar-fill"
                                    style={{ width: `${Math.max(0, Math.min(100, value.score))}%` }}
                                />
                            </div>
                            <small className="agent-dimension-explanation">{value.explanation}</small>
                        </div>
                    );
                })}
            </div>
        </section>
    );
}

function GatesView({ gates = [], t }) {
    if (!gates.length) return null;
    return (
        <section className="agent-gates-section">
            <h5>{t("agentWork.hardGatesTitle")}</h5>
            <div className="agent-gates-list">
                {gates.map((gate, index) => (
                    <article key={`${gate.dimension}-${index}`} className="agent-gate-card">
                        <div className="agent-gate-header">
                            <strong className="agent-gate-dimension">
                                {t(`jobs.analysis.dimension.${gate.dimension}`)}
                            </strong>
                            <span className={`agent-gate-decision gate-decision--${gate.status}`}>
                                {t(`agentWork.gate.${gate.status}`)}
                            </span>
                        </div>
                        <p className="agent-gate-reason">{gate.reason}</p>
                        {gate.quote_references?.length > 0 && (
                            <div className="agent-gate-quotes">
                                <span className="sub-label">{t("agentWork.advertQuotes")}:</span>
                                <ul>{gate.quote_references.map((quote, quoteIndex) => (
                                    <li key={`${quote}-${quoteIndex}`}>“{quote}”</li>
                                ))}</ul>
                            </div>
                        )}
                        <FactCitations factIds={gate.fact_ids} t={t} />
                        {gate.unknowns?.length > 0 && (
                            <div className="agent-gate-unknowns">
                                <span className="sub-label">{t("agentWork.unknowns")}:</span>
                                <ul>{gate.unknowns.map((unknown, unknownIndex) => (
                                    <li key={`${unknown}-${unknownIndex}`}>{unknown}</li>
                                ))}</ul>
                            </div>
                        )}
                    </article>
                ))}
            </div>
        </section>
    );
}

function DiscoveryProposalView({ payload, t, locale }) {
    return (
        <div className="agent-discovery-results">
            <h4>{t("agentWork.vacanciesProposed", { count: payload.listings.length })}</h4>
            <div className="agent-vacancies-list">
                {payload.listings.map((listing, index) => {
                    const safeUrl = safeExternalUrl(listing.external_url);
                    return (
                        <article key={`${listing.external_url}-${index}`} className="agent-vacancy-card">
                            <header className="agent-vacancy-card__header">
                                <div>
                                    <h5 className="agent-vacancy-title">{listing.title}</h5>
                                    <p className="agent-vacancy-meta">
                                        <span>{listing.company}</span>
                                        {listing.location && <span>{listing.location}</span>}
                                        <time dateTime={listing.observed_at}>
                                            {t("agentWork.observed")}: {new Date(listing.observed_at).toLocaleString(locale)}
                                        </time>
                                        {listing.source_platform && <span>{listing.source_platform}</span>}
                                    </p>
                                </div>
                                {safeUrl && (
                                    <a href={safeUrl} target="_blank" rel="noopener noreferrer" className="button button--secondary button--small">
                                        {t("agentWork.viewAdvert")}
                                    </a>
                                )}
                            </header>
                            <ScoreView scores={listing.scores} t={t} />
                            <GatesView gates={listing.gates} t={t} />
                            <details className="agent-vacancy-advert-details">
                                <summary>{t("agentWork.showCapturedAdvert")}</summary>
                                <pre tabIndex="0"><code>{listing.source_text}</code></pre>
                            </details>
                        </article>
                    );
                })}
            </div>
        </div>
    );
}

function AnalysisProposalView({ payload, t }) {
    return (
        <div className="agent-analysis-results">
            <p className="agent-analysis-recommendation">
                <strong>{t("agentWork.recommendation")}:</strong>{" "}
                {t(`agentWork.recommendation.${payload.recommendation}`)}
            </p>
            <ScoreView scores={payload.scores} t={t} />
            <GatesView gates={payload.gates} t={t} />
            <section className="agent-material-block">
                <h5>{t("agentWork.analysisClaims")}</h5>
                {payload.claims.map((claim, index) => (
                    <article key={`${claim.claim_text}-${index}`} className="agent-letter-para">
                        <p>{claim.claim_text}</p>
                        {claim.quote_text && <blockquote>“{claim.quote_text}”</blockquote>}
                        <FactCitations factIds={claim.fact_ids} t={t} />
                    </article>
                ))}
            </section>
        </div>
    );
}

function MaterialsProposalView({ payload, t }) {
    return (
        <div className="agent-materials-results">
            <p className="agent-material-preset-badge">
                <strong>{t("agentWork.templatePreset")}:</strong>{" "}
                {payload.preset_id} v{payload.preset_version} · {payload.locale.toUpperCase()}
            </p>
            <section className="agent-material-block">
                <h5>{t("agentWork.cvFacts")}</h5>
                <FactCitations factIds={payload.cv_selected_fact_ids} t={t} />
            </section>
            <section className="agent-material-block">
                <h5>{t("agentWork.cvOverrides")}</h5>
                <CitedTextList items={payload.cv_cited_overrides} t={t} />
            </section>
            <section className="agent-material-block">
                <h5>{t("agentWork.coverLetterProposal")}</h5>
                <CitedTextList items={payload.cover_letter} t={t} />
            </section>
            <section className="agent-material-block">
                <h5>{t("agentWork.emailDraft")}</h5>
                <p><strong>{t("agentWork.emailMode")}:</strong> {t(`agentWork.emailMode.${payload.email.mode}`)}</p>
                <p><strong>{t("agentWork.emailSubject")}:</strong> {payload.email.subject || t("agentWork.emptySubject")}</p>
                <CitedTextList items={payload.email.body} t={t} />
                <p><strong>{t("agentWork.emailAttachments")}:</strong>{" "}
                    {payload.email.attachment_names.length
                        ? payload.email.attachment_names.join(", ")
                        : t("agentWork.noAttachments")}
                </p>
            </section>
            <section className="agent-material-block">
                <h5>{t("agentWork.formAnswers")}</h5>
                {payload.questions_answers.length ? payload.questions_answers.map((answer) => (
                    <article key={answer.id} className="agent-answer-item">
                        <h6>{answer.question}</h6>
                        <p>{answer.text}</p>
                        <FactCitations factIds={answer.fact_ids} t={t} />
                    </article>
                )) : <p>{t("agentWork.noneProposed")}</p>}
            </section>
            <section className="agent-material-block">
                <h5>{t("agentWork.requirementsEvidence")}</h5>
                {payload.requirements_to_evidence.map((item, index) => (
                    <article key={`${item.requirement}-${index}`} className="agent-answer-item">
                        <h6>{item.requirement}</h6>
                        <blockquote>“{item.quote_text}”</blockquote>
                        <FactCitations factIds={item.fact_ids} t={t} />
                    </article>
                ))}
            </section>
            {payload.review_notes && (
                <section className="agent-material-block">
                    <h5>{t("agentWork.reviewNotes")}</h5>
                    <p>{payload.review_notes}</p>
                </section>
            )}
        </div>
    );
}

export function ProposalReview({
    work,
    proposal,
    onAccept,
    onReject,
    accepting = false,
    rejecting = false,
    errorMessage = "",
}) {
    const { t, language } = useI18n();
    const [confirmingReject, setConfirmingReject] = useState(false);
    if (!proposal) return <div className="state-panel"><p>{t("agentWork.proposalNotReturnedYet")}</p></div>;

    const payload = proposalPayload(proposal);
    const supported = proposalSupportsReview(work, proposal);
    const modelLabel = proposal.model_label ? ` (${proposal.model_label})` : "";
    const locale = language === "it" ? "it-IT" : "en-GB";

    return (
        <div className="agent-proposal-review" aria-labelledby="proposal-review-title">
            <header className="agent-proposal-header">
                <div>
                    <span className="section-kicker">{t("agentWork.proposalKicker")}</span>
                    <h3 id="proposal-review-title">{t("agentWork.proposalTitle")}</h3>
                </div>
                <div className="agent-proposal-provenance">
                    <span className="provenance-badge">
                        {proposal.client_label || t("agentWork.unspecifiedClient")}{modelLabel}
                    </span>
                    <time dateTime={proposal.created_at}>
                        {proposal.created_at ? new Date(proposal.created_at).toLocaleString(locale) : "—"}
                    </time>
                </div>
            </header>
            {errorMessage && <div className="agent-inline-error" role="alert">{errorMessage}</div>}
            {!supported && (
                <div className="agent-inline-error" role="alert">
                    <strong>{t("agentWork.unsupportedPayloadTitle")}</strong>
                    <p>{t("agentWork.unsupportedPayloadCopy")}</p>
                </div>
            )}
            {supported && payload.kind === "discover" && <DiscoveryProposalView payload={payload} t={t} locale={locale} />}
            {supported && payload.kind === "analyze" && <AnalysisProposalView payload={payload} t={t} />}
            {supported && payload.kind === "materials" && <MaterialsProposalView payload={payload} t={t} />}
            {work.state === "returned" && (
                <div className="agent-proposal-review-actions">
                    {confirmingReject ? (
                        <div role="group" aria-label={t("agentWork.confirmReject")}>
                            <p>{t("agentWork.rejectionConfirmCopy")}</p>
                            <button type="button" className="button button--secondary" onClick={() => setConfirmingReject(false)} disabled={rejecting}>
                                {t("common.cancel")}
                            </button>
                            <button type="button" className="button button--ghost text-danger" onClick={onReject} disabled={rejecting}>
                                {rejecting ? t("agentWork.rejecting") : t("agentWork.confirmReject")}
                            </button>
                        </div>
                    ) : (
                        <div className="d-flex gap-3 justify-content-end align-items-center flex-wrap">
                            <button type="button" className="button button--ghost text-danger" onClick={() => setConfirmingReject(true)} disabled={accepting || rejecting}>
                                {t("agentWork.rejectProposal")}
                            </button>
                            <button type="button" className="button button--primary" onClick={onAccept} disabled={!supported || accepting || rejecting}>
                                {accepting ? t("agentWork.accepting") : t("agentWork.acceptProposal")}
                            </button>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
