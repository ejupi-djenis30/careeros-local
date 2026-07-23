import { useEffect, useMemo, useState } from "react";
import { saveBlob } from "../../lib/download";
import { ApplicationService } from "../../services/applications";
import { CareerService } from "../../services/career";
import { factTitle } from "../career-profile/profileModel";
import { useI18n } from "../../i18n/useI18n";

let fallbackRowId = 0;
function rowId() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    fallbackRowId += 1;
    return `dossier-row-${fallbackRowId}`;
}

const requirementRow = () => ({ id: rowId(), requirement: "", evidenceFactIds: [] });
const answerRow = () => ({ id: rowId(), question: "", answer: "" });
const checklistRow = () => ({ id: rowId(), label: "", completed: false });
const trim = (value) => value.trim();
const LIMITS = Object.freeze({
    requirements: 25,
    evidencePerRequirement: 10,
    evidenceLinks: 100,
    uniqueFacts: 50,
    answers: 25,
    checklist: 50,
    coverLetter: 30000,
});

export function ApplicationDossier({ application, resumeVersions = [], resumeMetadataStatus = "ready", onRetryResumeMetadata, onChanged }) {
    const { t } = useI18n();
    const [facts, setFacts] = useState([]);
    const [requirements, setRequirements] = useState(() => [requirementRow()]);
    const [coverLetter, setCoverLetter] = useState("");
    const [answers, setAnswers] = useState(() => [answerRow()]);
    const [checklist, setChecklist] = useState(() => [checklistRow()]);
    const [busy, setBusy] = useState("");
    const [error, setError] = useState("");
    const [profileStatus, setProfileStatus] = useState("loading");
    const [profileLoadRevision, setProfileLoadRevision] = useState(0);
    const [evidenceNotice, setEvidenceNotice] = useState("");
    const [draftResumeVersionId, setDraftResumeVersionId] = useState(
        application.resume_version_id,
    );
    const linkedVersion = resumeVersions.find((version) => version.id === application.resume_version_id);
    const eligibleFacts = useMemo(() => {
        const selected = new Set(linkedVersion?.selected_fact_ids || []);
        return facts.filter((fact) => selected.has(fact.id) && fact.verification_status === "confirmed");
    }, [facts, linkedVersion]);
    const eligibleFactIds = useMemo(
        () => new Set(eligibleFacts.map((fact) => fact.id)),
        [eligibleFacts],
    );
    const selectedEvidenceIds = requirements.flatMap((row) => row.evidenceFactIds);
    const totalEvidenceLinks = selectedEvidenceIds.length;
    const uniqueEvidenceIds = new Set(selectedEvidenceIds);
    const staleEvidenceCount = selectedEvidenceIds.filter((factId) => !eligibleFactIds.has(factId)).length;

    useEffect(() => {
        const controller = new AbortController();
        CareerService.getProfile({ signal: controller.signal })
            .then((profile) => {
                if (controller.signal.aborted) return;
                setFacts(Array.isArray(profile.facts) ? profile.facts : []);
                setProfileStatus("ready");
            })
            .catch((profileError) => {
                if (controller.signal.aborted || profileError?.name === "AbortError") return;
                setProfileStatus("error");
            });
        return () => controller.abort();
    }, [profileLoadRevision]);

    if (profileStatus === "ready" && resumeMetadataStatus === "ready" && linkedVersion
        && draftResumeVersionId !== application.resume_version_id) {
        setDraftResumeVersionId(application.resume_version_id);
        setRequirements((current) => current.map((row) => ({
            ...row,
            evidenceFactIds: row.evidenceFactIds.filter((factId) => eligibleFactIds.has(factId)),
        })));
        setEvidenceNotice(staleEvidenceCount > 0
            ? t("dossier.evidenceReconciled", { count: staleEvidenceCount })
            : "");
    }

    const retryProfile = () => {
        setProfileStatus("loading");
        setProfileLoadRevision((current) => current + 1);
    };

    const updateRequirement = (id, field, value) => setRequirements((current) => current.map((row) => row.id === id ? { ...row, [field]: value } : row));
    const toggleFact = (rowIdValue, factId) => setRequirements((current) => current.map((row) => {
        if (row.id !== rowIdValue) return row;
        const selected = row.evidenceFactIds.includes(factId);
        if (!selected && (
            row.evidenceFactIds.length >= LIMITS.evidencePerRequirement
            || totalEvidenceLinks >= LIMITS.evidenceLinks
            || (!uniqueEvidenceIds.has(factId) && uniqueEvidenceIds.size >= LIMITS.uniqueFacts)
        )) return row;
        return {
            ...row,
            evidenceFactIds: selected
                ? row.evidenceFactIds.filter((value) => value !== factId)
                : [...row.evidenceFactIds, factId],
        };
    }));
    const updateAnswer = (id, field, value) => setAnswers((current) => current.map((row) => row.id === id ? { ...row, [field]: value } : row));
    const updateChecklist = (id, field, value) => setChecklist((current) => current.map((row) => row.id === id ? { ...row, [field]: value } : row));
    const removeRow = (setter, id) => setter((current) => current.filter((row) => row.id !== id));

    const requirementsReady = resumeMetadataStatus === "ready"
        && Boolean(linkedVersion)
        && profileStatus === "ready"
        && staleEvidenceCount === 0
        && requirements.length > 0
        && requirements.every((row) => trim(row.requirement) && row.evidenceFactIds.length > 0);

    const evidenceSelectionDisabled = (row, factId) => !row.evidenceFactIds.includes(factId) && (
        row.evidenceFactIds.length >= LIMITS.evidencePerRequirement
        || totalEvidenceLinks >= LIMITS.evidenceLinks
        || (!uniqueEvidenceIds.has(factId) && uniqueEvidenceIds.size >= LIMITS.uniqueFacts)
    );

    const publish = async (event) => {
        event.preventDefault();
        setError("");
        const incompleteAnswer = answers.some((row) => Boolean(trim(row.question)) !== Boolean(trim(row.answer)));
        if (incompleteAnswer) {
            setError(t("dossier.answerPairError"));
            return;
        }
        if (checklist.some((row) => row.completed && !trim(row.label))) {
            setError(t("dossier.checklistLabelError"));
            return;
        }
        setBusy("publish");
        try {
            const updated = await ApplicationService.publishDossier(application.id, {
                expected_revision: application.revision,
                cover_letter: trim(coverLetter) || null,
                answers: answers.filter((row) => trim(row.question) && trim(row.answer)).map((row) => ({ question: trim(row.question), answer: trim(row.answer) })),
                checklist: checklist.filter((row) => trim(row.label)).map((row) => ({ label: trim(row.label), completed: row.completed })),
                requirement_matrix: requirements.map((row) => ({ requirement: trim(row.requirement), evidence_fact_ids: row.evidenceFactIds })),
            });
            setRequirements([requirementRow()]);
            setCoverLetter("");
            setAnswers([answerRow()]);
            setChecklist([checklistRow()]);
            onChanged(updated);
        } catch (dossierError) {
            setError(dossierError.status === 409 ? t("applicationDetail.conflict") : dossierError.message);
        } finally {
            setBusy("");
        }
    };

    const download = async (dossier) => {
        setBusy(dossier.id);
        setError("");
        try {
            saveBlob(await ApplicationService.downloadDossier(application.id, dossier.id));
        } catch (downloadError) {
            setError(downloadError.message);
        } finally {
            setBusy("");
        }
    };

    return (
        <section className="application-operations" aria-labelledby="dossier-title">
            <header><div><span>{t("dossier.kicker")}</span><h3 id="dossier-title">{t("dossier.title")}</h3></div><i className="bi bi-shield-check" aria-hidden="true" /></header>
            <p>{t("dossier.copy")}</p>
            {error && <div className="inline-alert inline-alert--danger" role="alert">{error}</div>}
            {evidenceNotice && <div className="inline-alert" role="status" aria-live="polite">{evidenceNotice}</div>}
            {application.resume_version_id && resumeMetadataStatus === "error" && <div className="inline-alert inline-alert--danger" role="alert"><span>{t("dossier.resumeMetadataError")}</span> <button type="button" className="button button--secondary" onClick={onRetryResumeMetadata}>{t("dossier.retryResumeMetadata")}</button></div>}
            {profileStatus === "error" && <div className="inline-alert inline-alert--danger" role="alert"><span>{t("dossier.profileLoadError")}</span> <button type="button" className="button button--secondary" onClick={retryProfile}>{t("dossier.retryProfile")}</button></div>}
            {(application.dossiers || []).length > 0 && <div className="dossier-versions">{application.dossiers.map((dossier) => <article key={dossier.id}><div><strong>{t("dossier.version", { version: dossier.version_number })}</strong><span>{t("dossier.requirements", { count: dossier.requirement_count })} · {t("dossier.checklist", { complete: dossier.completed_checklist, total: dossier.checklist_total })}</span><code>{dossier.manifest_sha256.slice(0, 12)}</code></div><button type="button" className="button button--secondary" disabled={Boolean(busy)} onClick={() => download(dossier)}><i className="bi bi-file-earmark-zip" /> {t("dossier.download")}</button></article>)}</div>}
            {!application.resume_version_id ? <div className="empty-inline"><p>{t("dossier.resumeRequired")}</p></div> : (
                <form className="dossier-form" onSubmit={publish}>
                    <p id="dossier-limits" className="dossier-disclaimer">{t("dossier.limits")}</p>
                    <section className="dossier-builder" aria-labelledby="dossier-requirements-title">
                        <div className="dossier-builder__heading"><h4 id="dossier-requirements-title">{t("dossier.requirementsSection")}</h4><button type="button" className="button button--secondary" aria-describedby="dossier-limits" disabled={requirements.length >= LIMITS.requirements} onClick={() => setRequirements((current) => [...current, requirementRow()])}><i className="bi bi-plus-lg" aria-hidden="true" /> {t("dossier.addRequirement")}</button></div>
                        {requirements.map((row, index) => <fieldset className="dossier-row" key={row.id}>
                            <legend>{t("dossier.requirementNumber", { index: index + 1 })}</legend>
                            <label className="field-stack"><span>{t("dossier.requirementLabel", { index: index + 1 })}</span><textarea className="form-control" rows="2" value={row.requirement} onChange={(event) => updateRequirement(row.id, "requirement", event.target.value)} required maxLength="2000" placeholder={t("dossier.requirementPlaceholder")} /></label>
                            <fieldset className="dossier-evidence"><legend>{t("dossier.evidence")}</legend><small id={`dossier-evidence-limit-${row.id}`}>{t("dossier.evidenceLimit", { count: LIMITS.evidencePerRequirement })}</small>{resumeMetadataStatus === "loading" ? <p role="status">{t("dossier.resumeMetadataLoading")}</p> : resumeMetadataStatus === "error" ? null : !linkedVersion ? <p>{t("dossier.resumeMetadataMissing")}</p> : profileStatus === "loading" ? <p role="status">{t("dossier.loadingEvidence")}</p> : profileStatus === "ready" && eligibleFacts.length ? eligibleFacts.map((fact) => <label key={fact.id} className="check-line"><input type="checkbox" aria-label={t("dossier.evidenceFor", { fact: factTitle(fact), index: index + 1 })} aria-describedby={`dossier-evidence-limit-${row.id}`} checked={row.evidenceFactIds.includes(fact.id)} disabled={evidenceSelectionDisabled(row, fact.id)} onChange={() => toggleFact(row.id, fact.id)} /><span>{factTitle(fact)}</span><small>{t(`fact.type.${fact.fact_type}`)}</small></label>) : profileStatus === "ready" ? <p>{t("dossier.noEvidence")}</p> : null}</fieldset>
                            {requirements.length > 1 && <button type="button" className="button button--ghost dossier-row__remove" aria-label={t("dossier.removeRequirement", { index: index + 1 })} onClick={() => removeRow(setRequirements, row.id)}><i className="bi bi-trash3" aria-hidden="true" /> {t("dossier.remove")}</button>}
                        </fieldset>)}
                    </section>
                    <label className="field-stack"><span>{t("dossier.coverLetter")}</span><textarea className="form-control" rows="5" value={coverLetter} onChange={(event) => setCoverLetter(event.target.value)} maxLength={LIMITS.coverLetter} /></label>
                    <section className="dossier-builder" aria-labelledby="dossier-answers-title">
                        <div className="dossier-builder__heading"><h4 id="dossier-answers-title">{t("dossier.answersSection")}</h4><button type="button" className="button button--secondary" aria-describedby="dossier-limits" disabled={answers.length >= LIMITS.answers} onClick={() => setAnswers((current) => [...current, answerRow()])}><i className="bi bi-plus-lg" aria-hidden="true" /> {t("dossier.addAnswer")}</button></div>
                        {answers.map((row, index) => <fieldset className="dossier-row" key={row.id}>
                            <legend>{t("dossier.answerNumber", { index: index + 1 })}</legend>
                            <div className="form-grid form-grid--2"><label className="field-stack"><span>{t("dossier.questionLabel", { index: index + 1 })}</span><input className="form-control" value={row.question} onChange={(event) => updateAnswer(row.id, "question", event.target.value)} maxLength="1000" /></label><label className="field-stack"><span>{t("dossier.answerLabel", { index: index + 1 })}</span><textarea className="form-control" rows="2" value={row.answer} onChange={(event) => updateAnswer(row.id, "answer", event.target.value)} maxLength="20000" /></label></div>
                            {answers.length > 1 && <button type="button" className="button button--ghost dossier-row__remove" aria-label={t("dossier.removeAnswer", { index: index + 1 })} onClick={() => removeRow(setAnswers, row.id)}><i className="bi bi-trash3" aria-hidden="true" /> {t("dossier.remove")}</button>}
                        </fieldset>)}
                    </section>
                    <section className="dossier-builder" aria-labelledby="dossier-checklist-title">
                        <div className="dossier-builder__heading"><h4 id="dossier-checklist-title">{t("dossier.checklistSection")}</h4><button type="button" className="button button--secondary" aria-describedby="dossier-limits" disabled={checklist.length >= LIMITS.checklist} onClick={() => setChecklist((current) => [...current, checklistRow()])}><i className="bi bi-plus-lg" aria-hidden="true" /> {t("dossier.addChecklist")}</button></div>
                        {checklist.map((row, index) => <fieldset className="dossier-row dossier-checkline" key={row.id}>
                            <legend>{t("dossier.checklistNumber", { index: index + 1 })}</legend>
                            <label className="field-stack"><span>{t("dossier.checklistLabel", { index: index + 1 })}</span><input className="form-control" value={row.label} onChange={(event) => updateChecklist(row.id, "label", event.target.value)} maxLength="500" /></label><label className="check-line"><input type="checkbox" checked={row.completed} onChange={(event) => updateChecklist(row.id, "completed", event.target.checked)} /> {t("dossier.complete")}</label>
                            {checklist.length > 1 && <button type="button" className="button button--ghost dossier-row__remove" aria-label={t("dossier.removeChecklist", { index: index + 1 })} onClick={() => removeRow(setChecklist, row.id)}><i className="bi bi-trash3" aria-hidden="true" /> {t("dossier.remove")}</button>}
                        </fieldset>)}
                    </section>
                    <button className="button button--primary" disabled={Boolean(busy) || !requirementsReady}>{busy === "publish" ? t("dossier.publishing") : t("dossier.publish")}</button>
                    <small className="dossier-disclaimer">{t("dossier.disclaimer")}</small>
                </form>
            )}
        </section>
    );
}
