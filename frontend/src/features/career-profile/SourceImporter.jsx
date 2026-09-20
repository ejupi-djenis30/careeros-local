import { useEffect, useRef, useState } from "react";
import { CareerService } from "../../services/career";
import { useI18n } from "../../i18n/useI18n";
import { tReference } from "./referenceMessages";

function candidateLabel(candidate) {
    return candidate.payload?.name || candidate.payload?.title || candidate.fact_type;
}

function formatPreferenceValue(value) {
    if (Array.isArray(value)) {
        return value.join(", ");
    }
    if (typeof value === "boolean") {
        return value ? "Yes" : "No";
    }
    return String(value);
}

export function SourceImporter({
    firstRun = false,
    sectionNumber = "04",
    onAcceptCandidates = () => 0,
    onAcceptPreferences = () => 0,
    onPrepareImport = async () => {},
    onReviewAccepted,
    onReviewAcceptedPreferences,
}) {
    const { t, language } = useI18n();
    const tr = (key, vars) => tReference(key, language, vars);

    const [sourceRole, setSourceRole] = useState("profile");
    const [file, setFile] = useState(null);
    const [result, setResult] = useState(null);
    const [selectedFacts, setSelectedFacts] = useState(new Set());
    const [selectedPreferences, setSelectedPreferences] = useState(new Set());
    const [acceptedCount, setAcceptedCount] = useState(0);
    const [acceptedPrefCount, setAcceptedPrefCount] = useState(0);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const requestRef = useRef(0);

    useEffect(() => () => {
        requestRef.current += 1;
    }, []);

    const resetState = () => {
        setResult(null);
        setSelectedFacts(new Set());
        setSelectedPreferences(new Set());
        setAcceptedCount(0);
        setAcceptedPrefCount(0);
        setError("");
    };

    const upload = async () => {
        if (!file) return;
        const requestId = requestRef.current + 1;
        const selectedFile = file;
        const selectedRole = sourceRole;
        requestRef.current = requestId;
        setLoading(true);
        setError("");
        try {
            const prepared = await onPrepareImport();
            if (prepared === false || requestRef.current !== requestId) return;
            const imported = await CareerService.uploadSource(selectedFile, selectedRole);
            if (requestRef.current !== requestId) return;
            setResult(imported);
            setSelectedFacts(new Set());
            setSelectedPreferences(new Set());
            setAcceptedCount(0);
            setAcceptedPrefCount(0);
            setFile(null);
        } catch (uploadError) {
            if (requestRef.current === requestId) setError(uploadError.message);
        } finally {
            if (requestRef.current === requestId) setLoading(false);
        }
    };

    const toggleFact = (candidateId) => {
        setSelectedFacts((current) => {
            const next = new Set(current);
            if (next.has(candidateId)) next.delete(candidateId);
            else next.add(candidateId);
            return next;
        });
    };

    const togglePreference = (candidateId) => {
        setSelectedPreferences((current) => {
            const next = new Set(current);
            if (next.has(candidateId)) next.delete(candidateId);
            else next.add(candidateId);
            return next;
        });
    };

    const acceptFacts = () => {
        const candidates = (result?.candidates || []).filter((item) => selectedFacts.has(item.candidate_id));
        const count = onAcceptCandidates(result, candidates);
        setAcceptedCount(Number.isFinite(count) ? count : candidates.length);
        setSelectedFacts(new Set());
    };

    const acceptPreferences = () => {
        const candidates = (result?.preference_candidates || []).filter((item) => selectedPreferences.has(item.candidate_id));
        const count = onAcceptPreferences(result, candidates);
        const accepted = Number.isFinite(count) ? count : candidates.length;
        setAcceptedPrefCount(accepted);
        if (accepted > 0) setSelectedPreferences(new Set());
    };

    const showFactSection = !result || result.source_role === "profile" || (result.candidates || []).length > 0;
    const showPrefSection = result && (result.source_role === "goals" || (result.preference_candidates || []).length > 0);

    return (
        <section id="source-import" className={`surface-section ${firstRun ? "source-first-run" : ""}`} aria-labelledby="sources-title">
            <div className="section-heading">
                <div>
                    <span className="section-kicker">{t(firstRun ? "source.firstRunKicker" : "source.kicker")}</span>
                    <h2 id="sources-title" tabIndex="-1">{t(firstRun ? "source.firstRunTitle" : "source.title")}</h2>
                </div>
                {sectionNumber && <span className="section-number">{sectionNumber}</span>}
            </div>
            <p className="section-intro">{t("source.copy")}</p>
            {firstRun && (
                <p className="source-first-run__notice">
                    <i className="bi bi-shield-check" aria-hidden="true" />
                    {t("source.firstRunCopy")}
                </p>
            )}

            <div className="source-role-selector" style={{ marginBottom: "1rem" }}>
                <label htmlFor="source-role-select" style={{ display: "block", marginBottom: "0.35rem", fontWeight: 600 }}>
                    {tr("source.role")}
                </label>
                <select
                    id="source-role-select"
                    className="input-select"
                    value={sourceRole}
                    disabled={loading}
                    onChange={(event) => {
                        requestRef.current += 1;
                        setSourceRole(event.target.value);
                        resetState();
                    }}
                    style={{ maxWidth: "320px", width: "100%", padding: "0.4rem 0.6rem" }}
                >
                    <option value="profile">{tr("source.role.profile")}</option>
                    <option value="narrative">{tr("source.role.narrative")}</option>
                    <option value="goals">{tr("source.role.goals")}</option>
                    <option value="template_reference">{tr("source.role.template_reference")}</option>
                </select>
                <p className="field-hint" style={{ fontSize: "0.85rem", color: "var(--color-text-muted, #6c757d)", marginTop: "0.25rem" }}>
                    {tr(`source.role.${sourceRole}Desc`)}
                </p>
            </div>

            <div
                className="source-disclosure"
                role="note"
                style={{
                    fontSize: "0.85rem",
                    padding: "0.5rem 0.75rem",
                    background: "var(--color-bg-subtle, #f8f9fa)",
                    borderLeft: "3px solid var(--color-primary, #0d6efd)",
                    marginBottom: "1rem",
                    borderRadius: "2px",
                }}
            >
                <i className="bi bi-info-circle" aria-hidden="true" style={{ marginRight: "0.5rem" }} />
                <span>{tr("source.deterministicDisclosure")}</span>
            </div>

            <div className="upload-row">
                <label className="file-picker">
                    <i className="bi bi-file-earmark-arrow-up" aria-hidden="true" />
                    <span>{file ? file.name : t("source.choose")}</span>
                    <input
                        aria-label={t("source.file")}
                        type="file"
                        disabled={loading}
                        accept=".txt,.md,.pdf,.docx,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        onChange={(event) => {
                            requestRef.current += 1;
                            setFile(event.target.files?.[0] || null);
                            resetState();
                        }}
                    />
                </label>
                <button
                    type="button"
                    className="button button--secondary"
                    disabled={!file || loading}
                    onClick={upload}
                >
                    {loading ? t("source.importing") : t("source.import")}
                </button>
            </div>

            {error && <div className="inline-alert inline-alert--danger" role="alert">{error}</div>}

            {result && (
                <div className="source-review">
                    <div className="source-result">
                        <i className="bi bi-check2-circle" aria-hidden="true" />
                        <div>
                            <strong>{result.original_name}</strong>
                            <span>
                                {t("source.characters", { count: result.extracted_characters?.toLocaleString() })} · SHA-256 {result.sha256?.slice(0, 12)}… · <em>{tr(`source.role.${result.source_role || "profile"}`)}</em>
                            </span>
                        </div>
                    </div>

                    <details className="source-preview">
                        <summary>{t("source.preview")}</summary>
                        <pre>{result.text_preview || t("source.noText")}</pre>
                    </details>

                    {result.warnings && result.warnings.length > 0 && (
                        <div className="inline-alert inline-alert--warning" role="alert" style={{ marginTop: "0.75rem" }}>
                            <strong>{tr("source.warningsTitle")}</strong>
                            <ul style={{ margin: "0.25rem 0 0 1.25rem", padding: 0 }}>
                                {result.warnings.map((w, idx) => (
                                    <li key={idx}>{w}</li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {result.review_notes && result.review_notes.length > 0 && (
                        <details className="source-preview" style={{ marginTop: "0.5rem" }}>
                            <summary>{tr("source.reviewNotesTitle")} ({result.review_notes.length})</summary>
                            <ul style={{ margin: "0.5rem 0 0 1.25rem" }}>
                                {result.review_notes.map((note, idx) => (
                                    <li key={idx} style={{ fontSize: "0.85rem", marginBottom: "0.25rem" }}>{note}</li>
                                ))}
                            </ul>
                        </details>
                    )}

                    {showFactSection && (
                        <div className="source-candidates" aria-labelledby="source-candidates-title">
                            <div>
                                <strong id="source-candidates-title">{t("source.candidates")}</strong>
                                <span>{t("source.candidatesCopy")}</span>
                            </div>
                            {(result.candidates || []).length === 0 ? (
                                <p>{t("source.noCandidates")}</p>
                            ) : (
                                result.candidates.map((candidate) => (
                                    <label className="source-candidate" key={candidate.candidate_id}>
                                        <input
                                            type="checkbox"
                                            checked={selectedFacts.has(candidate.candidate_id)}
                                            onChange={() => toggleFact(candidate.candidate_id)}
                                        />
                                        <span>
                                            <strong>{candidateLabel(candidate)}</strong>
                                            <small>
                                                {t(`fact.type.${candidate.fact_type}`)} · {t("source.confidence", { value: Math.round(candidate.confidence * 100) })} · {candidate.source_locator}
                                            </small>
                                            <em>{candidate.excerpt}</em>
                                        </span>
                                    </label>
                                ))
                            )}
                            {(result.candidates || []).length > 0 && (
                                <button
                                    type="button"
                                    className="button button--primary"
                                    disabled={selectedFacts.size === 0}
                                    onClick={acceptFacts}
                                >
                                    {t("source.accept", { count: selectedFacts.size })}
                                </button>
                            )}
                            {acceptedCount > 0 && (
                                <div className="source-accepted">
                                    <p role="status">
                                        {t(acceptedCount === 1 ? "source.acceptedOne" : "source.acceptedMany", { count: acceptedCount })}
                                    </p>
                                    {onReviewAccepted && (
                                        <button type="button" className="button button--secondary button--small" onClick={onReviewAccepted}>
                                            {t("source.reviewAccepted")}
                                            <i className="bi bi-arrow-right" aria-hidden="true" />
                                        </button>
                                    )}
                                </div>
                            )}
                        </div>
                    )}

                    {showPrefSection && (
                        <div className="source-candidates" aria-labelledby="source-preference-candidates-title" style={{ marginTop: "1rem" }}>
                            <div>
                                <strong id="source-preference-candidates-title">{tr("source.preferenceCandidates")}</strong>
                                <span>{tr("source.preferenceCandidatesCopy")}</span>
                                <span>{tr("source.preferenceMergePolicy")}</span>
                            </div>
                            {(result.preference_candidates || []).length === 0 ? (
                                <p>{tr("source.noPreferences")}</p>
                            ) : (
                                result.preference_candidates.map((cand) => (
                                    <label className="source-candidate" key={cand.candidate_id}>
                                        <input
                                            type="checkbox"
                                            checked={selectedPreferences.has(cand.candidate_id)}
                                            onChange={() => togglePreference(cand.candidate_id)}
                                        />
                                        <span>
                                            <strong>{tr(`source.prefField.${cand.field}`) || cand.field}: {formatPreferenceValue(cand.value)}</strong>
                                            <small>{cand.source_locator}</small>
                                            <em>{cand.excerpt}</em>
                                        </span>
                                    </label>
                                ))
                            )}
                            {(result.preference_candidates || []).length > 0 && (
                                <button
                                    type="button"
                                    className="button button--primary"
                                    disabled={selectedPreferences.size === 0}
                                    onClick={acceptPreferences}
                                >
                                    {tr("source.acceptPreferences", { count: selectedPreferences.size })}
                                </button>
                            )}
                            {acceptedPrefCount > 0 && (
                                <div className="source-accepted">
                                    <p role="status">
                                        {tr("source.acceptedPreferences", { count: acceptedPrefCount })}
                                    </p>
                                    {onReviewAcceptedPreferences && (
                                        <button type="button" className="button button--secondary button--small" onClick={onReviewAcceptedPreferences}>
                                            {tr("source.reviewAcceptedPreferences")}
                                            <i className="bi bi-arrow-right" aria-hidden="true" />
                                        </button>
                                    )}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}
        </section>
    );
}
