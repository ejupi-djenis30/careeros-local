import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
const blankForm = () => ({
    requirements: [requirementRow()],
    coverLetter: "",
    answers: [answerRow()],
    checklist: [checklistRow()],
});
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
const AUTOSAVE_DELAY_MS = 650;

function draftContent({ requirements, coverLetter, answers, checklist }) {
    return {
        cover_letter: coverLetter || null,
        answers: answers.map((row) => ({
            client_id: row.id,
            question: row.question,
            answer: row.answer,
        })),
        checklist: checklist.map((row) => ({
            client_id: row.id,
            label: row.label,
            completed: row.completed,
        })),
        requirement_matrix: requirements.map((row) => ({
            client_id: row.id,
            requirement: row.requirement,
            evidence_fact_ids: row.evidenceFactIds,
        })),
    };
}

function formFromDraft(draft) {
    const content = draft?.content || {};
    return {
        requirements: (content.requirement_matrix || []).map((row) => ({
            id: row.client_id,
            requirement: row.requirement,
            evidenceFactIds: row.evidence_fact_ids,
        })),
        coverLetter: content.cover_letter || "",
        answers: (content.answers || []).map((row) => ({
            id: row.client_id,
            question: row.question,
            answer: row.answer,
        })),
        checklist: (content.checklist || []).map((row) => ({
            id: row.client_id,
            label: row.label,
            completed: row.completed,
        })),
    };
}

export function ApplicationDossier({ application, resumeVersions = [], resumeMetadataStatus = "ready", onRetryResumeMetadata, onChanged }) {
    const { t } = useI18n();
    const initial = useMemo(() => blankForm(), []);
    const [facts, setFacts] = useState([]);
    const [requirements, setRequirements] = useState(initial.requirements);
    const [coverLetter, setCoverLetter] = useState(initial.coverLetter);
    const [answers, setAnswers] = useState(initial.answers);
    const [checklist, setChecklist] = useState(initial.checklist);
    const [busy, setBusy] = useState("");
    const [error, setError] = useState("");
    const [profileStatus, setProfileStatus] = useState("loading");
    const [profileLoadRevision, setProfileLoadRevision] = useState(0);
    const [evidenceNotice, setEvidenceNotice] = useState("");
    const [draftResumeVersionId, setDraftResumeVersionId] = useState(application.resume_version_id);
    const [draftStatus, setDraftStatus] = useState("loading");
    const [draftRevision, setDraftRevision] = useState(null);
    const [draftLoadedFor, setDraftLoadedFor] = useState("");
    const [draftLoadAttempt, setDraftLoadAttempt] = useState(0);
    const activeApplicationRef = useRef(application.id);
    const draftRevisionRef = useRef(null);
    const savedFingerprintRef = useRef("");
    const savedApplicationRevisionRef = useRef(null);
    const currentFingerprintRef = useRef("");
    const savePromiseRef = useRef(null);

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
    const currentDraftContent = useMemo(
        () => draftContent({ requirements, coverLetter, answers, checklist }),
        [requirements, coverLetter, answers, checklist],
    );
    const currentDraftFingerprint = useMemo(
        () => JSON.stringify(currentDraftContent),
        [currentDraftContent],
    );
    useEffect(() => {
        currentFingerprintRef.current = currentDraftFingerprint;
    }, [currentDraftFingerprint]);

    const applyForm = useCallback((form) => {
        setRequirements(form.requirements.length ? form.requirements : [requirementRow()]);
        setCoverLetter(form.coverLetter);
        setAnswers(form.answers.length ? form.answers : [answerRow()]);
        setChecklist(form.checklist.length ? form.checklist : [checklistRow()]);
    }, []);

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

    useEffect(() => {
        const applicationId = application.id;
        activeApplicationRef.current = applicationId;
        if (draftLoadedFor === applicationId) return undefined;
        const controller = new AbortController();
        Promise.resolve()
            .then(() => {
                if (controller.signal.aborted) return null;
                setDraftStatus("loading");
                setEvidenceNotice("");
                return ApplicationService.getDossierDraft(
                    applicationId,
                    { signal: controller.signal },
                );
            })
            .then((draft) => {
                if (controller.signal.aborted || activeApplicationRef.current !== applicationId) return;
                const form = draft ? formFromDraft(draft) : blankForm();
                applyForm(form);
                const fingerprint = JSON.stringify(draftContent(form));
                draftRevisionRef.current = draft?.revision ?? null;
                savedFingerprintRef.current = fingerprint;
                savedApplicationRevisionRef.current = draft?.application_revision ?? application.revision;
                setDraftRevision(draft?.revision ?? null);
                setDraftResumeVersionId(draft?.resume_version_id ?? application.resume_version_id);
                setDraftLoadedFor(applicationId);
                setDraftStatus(draft ? "saved" : "empty");
            })
            .catch(() => {
                if (controller.signal.aborted || activeApplicationRef.current !== applicationId) return;
                setDraftStatus("load-error");
            });
        return () => {
            controller.abort();
            if (activeApplicationRef.current === applicationId) activeApplicationRef.current = "";
        };
    }, [
        application.id,
        application.resume_version_id,
        application.revision,
        applyForm,
        draftLoadAttempt,
        draftLoadedFor,
    ]);

    useEffect(() => {
        if (profileStatus !== "ready" || resumeMetadataStatus !== "ready" || !linkedVersion
            || draftResumeVersionId === application.resume_version_id) return;
        const applicationId = application.id;
        Promise.resolve().then(() => {
            if (activeApplicationRef.current !== applicationId) return;
            setDraftResumeVersionId(application.resume_version_id);
            setRequirements((current) => current.map((row) => ({
                ...row,
                evidenceFactIds: row.evidenceFactIds.filter((factId) => eligibleFactIds.has(factId)),
            })));
            setEvidenceNotice(staleEvidenceCount > 0
                ? t("dossier.evidenceReconciled", { count: staleEvidenceCount })
                : "");
        });
    }, [
        application.id,
        application.resume_version_id,
        draftResumeVersionId,
        eligibleFactIds,
        linkedVersion,
        profileStatus,
        resumeMetadataStatus,
        staleEvidenceCount,
        t,
    ]);

    const saveDraftSnapshot = useCallback(async (content, fingerprint) => {
        if (savePromiseRef.current) {
            try {
                await savePromiseRef.current;
            } catch {
                // A new explicit retry is allowed after the prior attempt settles.
            }
        }
        const alreadyCurrent = savedFingerprintRef.current === fingerprint
            && savedApplicationRevisionRef.current === application.revision
            && draftRevisionRef.current !== null;
        if (alreadyCurrent) return draftRevisionRef.current;

        setDraftStatus("saving");
        const operation = ApplicationService.saveDossierDraft(application.id, {
            expected_revision: draftRevisionRef.current,
            expected_application_revision: application.revision,
            resume_version_id: application.resume_version_id,
            content,
        });
        savePromiseRef.current = operation;
        try {
            const stored = await operation;
            if (activeApplicationRef.current !== application.id) return stored.revision;
            draftRevisionRef.current = stored.revision;
            savedFingerprintRef.current = fingerprint;
            savedApplicationRevisionRef.current = stored.application_revision;
            setDraftRevision(stored.revision);
            setDraftResumeVersionId(stored.resume_version_id);
            setDraftStatus(
                currentFingerprintRef.current === fingerprint ? "saved" : "unsaved",
            );
            return stored.revision;
        } catch (saveError) {
            if (activeApplicationRef.current === application.id) {
                setDraftStatus(saveError.status === 409 ? "conflict" : "save-error");
            }
            throw saveError;
        } finally {
            if (savePromiseRef.current === operation) savePromiseRef.current = null;
        }
    }, [
        application.id,
        application.resume_version_id,
        application.revision,
    ]);

    useEffect(() => {
        if (
            draftLoadedFor !== application.id
            || !application.resume_version_id
            || ["loading", "saving", "save-error", "load-error", "conflict"].includes(
                draftStatus,
            )
        ) return undefined;
        const contentChanged = savedFingerprintRef.current !== currentDraftFingerprint;
        const savedDraftNeedsRebase = draftRevisionRef.current !== null
            && savedApplicationRevisionRef.current !== application.revision;
        if (!contentChanged && !savedDraftNeedsRebase) return undefined;
        setDraftStatus("unsaved");
        const timeout = window.setTimeout(() => {
            saveDraftSnapshot(currentDraftContent, currentDraftFingerprint).catch(() => {});
        }, AUTOSAVE_DELAY_MS);
        return () => window.clearTimeout(timeout);
    }, [
        application.id,
        application.resume_version_id,
        application.revision,
        currentDraftContent,
        currentDraftFingerprint,
        draftLoadedFor,
        draftStatus,
        saveDraftSnapshot,
    ]);

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
        && draftLoadedFor === application.id
        && staleEvidenceCount === 0
        && requirements.length > 0
        && requirements.every((row) => trim(row.requirement) && row.evidenceFactIds.length > 0);
    const evidenceSelectionDisabled = (row, factId) => !row.evidenceFactIds.includes(factId) && (
        row.evidenceFactIds.length >= LIMITS.evidencePerRequirement
        || totalEvidenceLinks >= LIMITS.evidenceLinks
        || (!uniqueEvidenceIds.has(factId) && uniqueEvidenceIds.size >= LIMITS.uniqueFacts)
    );

    const retryDraftSave = async () => {
        try {
            await saveDraftSnapshot(currentDraftContent, currentDraftFingerprint);
        } catch {
            // The visible save status preserves the form and explains the retry state.
        }
    };

    const keepLocalDraftAfterConflict = async () => {
        setDraftStatus("saving");
        try {
            const serverDraft = await ApplicationService.getDossierDraft(application.id);
            draftRevisionRef.current = serverDraft?.revision ?? null;
            setDraftRevision(serverDraft?.revision ?? null);
            await saveDraftSnapshot(currentDraftContent, currentDraftFingerprint);
        } catch (draftError) {
            setDraftStatus(draftError.status === 409 ? "conflict" : "save-error");
        }
    };

    const discardDraft = async () => {
        if (draftRevisionRef.current === null) return;
        setBusy("discard");
        try {
            await ApplicationService.deleteDossierDraft(
                application.id,
                draftRevisionRef.current,
            );
            const form = blankForm();
            applyForm(form);
            const fingerprint = JSON.stringify(draftContent(form));
            draftRevisionRef.current = null;
            savedFingerprintRef.current = fingerprint;
            savedApplicationRevisionRef.current = application.revision;
            setDraftRevision(null);
            setDraftStatus("empty");
            setError("");
        } catch (deleteError) {
            setDraftStatus(deleteError.status === 409 ? "conflict" : "save-error");
        } finally {
            setBusy("");
        }
    };

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
            const savedRevision = await saveDraftSnapshot(
                currentDraftContent,
                currentDraftFingerprint,
            );
            const updated = await ApplicationService.publishDossier(application.id, {
                expected_revision: application.revision,
                expected_draft_revision: savedRevision,
                cover_letter: trim(coverLetter) || null,
                answers: answers.filter((row) => trim(row.question) && trim(row.answer)).map((row) => ({ question: trim(row.question), answer: trim(row.answer) })),
                checklist: checklist.filter((row) => trim(row.label)).map((row) => ({ label: trim(row.label), completed: row.completed })),
                requirement_matrix: requirements.map((row) => ({ requirement: trim(row.requirement), evidence_fact_ids: row.evidenceFactIds })),
            });
            const form = blankForm();
            applyForm(form);
            draftRevisionRef.current = null;
            savedFingerprintRef.current = JSON.stringify(draftContent(form));
            savedApplicationRevisionRef.current = updated.revision;
            setDraftRevision(null);
            setDraftStatus("empty");
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

    const draftStatusKey = {
        loading: "dossier.draftLoading",
        empty: "dossier.draftEmpty",
        unsaved: "dossier.draftUnsaved",
        saving: "dossier.draftSaving",
        saved: "dossier.draftSaved",
        "save-error": "dossier.draftSaveError",
        "load-error": "dossier.draftLoadError",
        conflict: "dossier.draftConflict",
    }[draftStatus];
    const draftStatusIsError = ["save-error", "load-error", "conflict"].includes(draftStatus);

    return (
        <section className="application-operations" aria-labelledby="dossier-title">
            <header><div><span>{t("dossier.kicker")}</span><h3 id="dossier-title">{t("dossier.title")}</h3></div><i className="bi bi-shield-check" aria-hidden="true" /></header>
            <p>{t("dossier.copy")}</p>
            {error && <div className="inline-alert inline-alert--danger" role="alert">{error}</div>}
            {evidenceNotice && <div className="inline-alert" role="status" aria-live="polite">{evidenceNotice}</div>}
            {application.resume_version_id && <div className={`dossier-save-status dossier-save-status--${draftStatus}`} role={draftStatusIsError ? "alert" : "status"} aria-live="polite"><span><i className={`bi ${draftStatus === "saved" ? "bi-device-ssd-fill" : draftStatusIsError ? "bi-exclamation-triangle" : "bi-device-ssd"}`} aria-hidden="true" /> {t(draftStatusKey)}</span><div>{draftStatus === "load-error" && <button type="button" className="button button--ghost" onClick={() => setDraftLoadAttempt((value) => value + 1)}>{t("dossier.retryDraftLoad")}</button>}{draftStatus === "save-error" && <button type="button" className="button button--ghost" onClick={retryDraftSave}>{t("dossier.retryDraftSave")}</button>}{draftStatus === "conflict" && <button type="button" className="button button--ghost" onClick={keepLocalDraftAfterConflict}>{t("dossier.keepLocalDraft")}</button>}{draftRevision !== null && <button type="button" className="button button--ghost" disabled={Boolean(busy) || draftStatus === "saving"} onClick={discardDraft}>{t("dossier.discardDraft")}</button>}</div></div>}
            {application.resume_version_id && resumeMetadataStatus === "error" && <div className="inline-alert inline-alert--danger" role="alert"><span>{t("dossier.resumeMetadataError")}</span> <button type="button" className="button button--secondary" onClick={onRetryResumeMetadata}>{t("dossier.retryResumeMetadata")}</button></div>}
            {profileStatus === "error" && <div className="inline-alert inline-alert--danger" role="alert"><span>{t("dossier.profileLoadError")}</span> <button type="button" className="button button--secondary" onClick={retryProfile}>{t("dossier.retryProfile")}</button></div>}
            {(application.dossiers || []).length > 0 && <div className="dossier-versions">{application.dossiers.map((dossier) => <article key={dossier.id}><div><strong>{t("dossier.version", { version: dossier.version_number })}</strong><span>{t("dossier.requirements", { count: dossier.requirement_count })} · {t("dossier.checklist", { complete: dossier.completed_checklist, total: dossier.checklist_total })}</span><code>{dossier.manifest_sha256.slice(0, 12)}</code></div><button type="button" className="button button--secondary" disabled={Boolean(busy)} onClick={() => download(dossier)}><i className="bi bi-file-earmark-zip" /> {t("dossier.download")}</button></article>)}</div>}
            {!application.resume_version_id ? <div className="empty-inline"><p>{t("dossier.resumeRequired")}</p></div> : (
                <form className="dossier-form" onSubmit={publish} aria-busy={draftStatus === "loading" || draftStatus === "saving"}>
                    <fieldset className="dossier-form__workspace" disabled={draftStatus === "loading" || draftStatus === "load-error"}>
                        <legend className="visually-hidden">{t("dossier.workspace")}</legend>
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
                    </fieldset>
                </form>
            )}
        </section>
    );
}
