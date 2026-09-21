import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { saveBlob } from "../../lib/download";
import { ApplicationService } from "../../services/applications";
import { CareerService } from "../../services/career";
import { DossierFields } from "./DossierFields";
import { DossierMaterials } from "./DossierMaterials";
import { DossierTarget } from "./DossierTarget";
import { DossierArtifacts } from "./DossierArtifacts";
import { LIMITS, requirementRow, answerRow, checklistRow, blankForm, draftContent, formFromDraft, draftBinding, publishContent } from "./dossierModel";
import { useI18n } from "../../i18n/useI18n";

const AUTOSAVE_DELAY_MS = 650;
const trim = (value) => value.trim();

export function ApplicationDossier({ application, resumeVersions = [], resumeDrafts = [], resumeMetadataStatus = "ready", onRetryResumeMetadata, onChanged }) {
    const { t } = useI18n();
    const initial = useMemo(() => blankForm(), []);
    const [facts, setFacts] = useState([]);
    const [requirements, setRequirements] = useState(initial.requirements);
    const [coverLetter, setCoverLetter] = useState(initial.coverLetter);
    const [answers, setAnswers] = useState(initial.answers);
    const [checklist, setChecklist] = useState(initial.checklist);
    const [letterOptions, setLetterOptions] = useState(null);
    const [emailDraft, setEmailDraft] = useState(null);
    const [evidenceClaims, setEvidenceClaims] = useState([]);
    const [generationProvenance, setGenerationProvenance] = useState(null);
    const [binding, setBinding] = useState(() => draftBinding(null, application));
    const [publishVersionId, setPublishVersionId] = useState("");
    const [incomingDraft, setIncomingDraft] = useState(null);
    const [busy, setBusy] = useState("");
    const [error, setError] = useState("");
    const [profileStatus, setProfileStatus] = useState("loading");
    const [profileLoadRevision, setProfileLoadRevision] = useState(0);
    const [evidenceNotice, setEvidenceNotice] = useState("");
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

    useEffect(() => {
        activeApplicationRef.current = application.id;
        return () => { activeApplicationRef.current = ""; };
    }, [application.id]);

    const hasBinding = Boolean(binding.resume_draft_id || binding.resume_version_id);
    const linkedVersion = binding.resume_draft_id
        ? resumeDrafts.find((draft) => draft.id === binding.resume_draft_id)
        : resumeVersions.find((version) => version.id === application.resume_version_id);
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
        () => draftContent({ requirements, coverLetter, answers, checklist, letterOptions, emailDraft, evidenceClaims, generationProvenance }),
        [requirements, coverLetter, answers, checklist, letterOptions, emailDraft, evidenceClaims, generationProvenance],
    );
    const currentDraftFingerprint = useMemo(
        () => JSON.stringify({ content: currentDraftContent, binding }),
        [currentDraftContent, binding],
    );
    useEffect(() => {
        currentFingerprintRef.current = currentDraftFingerprint;
    }, [currentDraftFingerprint]);

    const applyForm = useCallback((form) => {
        setRequirements(form.requirements.length ? form.requirements : [requirementRow()]);
        setCoverLetter(form.coverLetter);
        setAnswers(form.answers.length ? form.answers : [answerRow()]);
        setChecklist(form.checklist.length ? form.checklist : [checklistRow()]);
        setLetterOptions(form.letterOptions);
        setEmailDraft(form.emailDraft);
        setEvidenceClaims(form.evidenceClaims);
        setGenerationProvenance(form.generationProvenance);
    }, []);

    const installDraft = useCallback((draft) => {
        const form = draft ? formFromDraft(draft) : blankForm();
        if (!form.answers.length) form.answers = [answerRow()];
        if (!form.checklist.length) form.checklist = [checklistRow()];
        const nextBinding = draftBinding(draft, application);
        applyForm(form);
        setBinding(nextBinding);
        setPublishVersionId("");
        draftRevisionRef.current = draft?.revision ?? null;
        savedFingerprintRef.current = JSON.stringify({ content: draftContent(form), binding: nextBinding });
        savedApplicationRevisionRef.current = draft?.application_revision ?? application.revision;
        setDraftRevision(draft?.revision ?? null);
        setDraftLoadedFor(application.id);
        setDraftStatus(draft ? "saved" : "empty");
        setIncomingDraft(null);
        setBusy("");
    }, [application, applyForm]);

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
                installDraft(draft);
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
        installDraft,
    ]);

    useEffect(() => {
        if (profileStatus !== "ready" || resumeMetadataStatus !== "ready" || !linkedVersion
            || binding.resume_draft_id || binding.resume_version_id === application.resume_version_id) return;
        const applicationId = application.id;
        Promise.resolve().then(() => {
            if (activeApplicationRef.current !== applicationId) return;
            setBinding({ resume_version_id: application.resume_version_id });
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
        binding,
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
        if (activeApplicationRef.current !== application.id) throw new DOMException("Aborted", "AbortError");
        const alreadyCurrent = savedFingerprintRef.current === fingerprint
            && savedApplicationRevisionRef.current === application.revision
            && draftRevisionRef.current !== null;
        if (alreadyCurrent) return draftRevisionRef.current;

        setDraftStatus("saving");
        const operation = ApplicationService.saveDossierDraft(application.id, {
            expected_revision: draftRevisionRef.current,
            expected_application_revision: application.revision,
            ...binding,
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
        application.revision,
        binding,
    ]);

    useEffect(() => {
        if (
            draftLoadedFor !== application.id
            || !hasBinding || busy || incomingDraft
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
        hasBinding,
        busy,
        incomingDraft,
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
        && (!binding.resume_draft_id || Boolean(publishVersionId))
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
            if (activeApplicationRef.current !== application.id) return;
            draftRevisionRef.current = serverDraft?.revision ?? null;
            setDraftRevision(serverDraft?.revision ?? null);
            await saveDraftSnapshot(currentDraftContent, currentDraftFingerprint);
        } catch (draftError) {
            if (activeApplicationRef.current !== application.id) return;
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
            if (activeApplicationRef.current !== application.id) return;
            const form = blankForm();
            applyForm(form);
            const fingerprint = JSON.stringify({ content: draftContent(form), binding });
            draftRevisionRef.current = null;
            savedFingerprintRef.current = fingerprint;
            savedApplicationRevisionRef.current = application.revision;
            setDraftRevision(null);
            setDraftStatus("empty");
            setError("");
        } catch (deleteError) {
            if (activeApplicationRef.current !== application.id) return;
            setDraftStatus(deleteError.status === 409 ? "conflict" : "save-error");
        } finally {
            if (activeApplicationRef.current === application.id) setBusy("");
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
            if (activeApplicationRef.current !== application.id) return;
            const updated = await ApplicationService.publishDossier(application.id, {
                expected_revision: application.revision,
                expected_draft_revision: savedRevision,
                ...(binding.resume_draft_id ? { resume_version_id: publishVersionId } : {}),
                ...publishContent(currentDraftContent),
            });
            if (activeApplicationRef.current !== application.id) return;
            const form = blankForm();
            applyForm(form);
            draftRevisionRef.current = null;
            const nextBinding = draftBinding(null, updated);
            setBinding(nextBinding);
            savedFingerprintRef.current = JSON.stringify({ content: draftContent(form), binding: nextBinding });
            savedApplicationRevisionRef.current = updated.revision;
            setDraftRevision(null);
            setDraftStatus("empty");
            onChanged(updated);
        } catch (dossierError) {
            if (activeApplicationRef.current !== application.id) return;
            setError(dossierError.status === 409 ? t("applicationDetail.conflict") : dossierError.message);
        } finally {
            if (activeApplicationRef.current === application.id) setBusy("");
        }
    };

    const download = async (dossier, filename) => {
        setBusy(dossier.id);
        setError("");
        try {
            const downloaded = filename
                ? await ApplicationService.downloadDossierArtifact(application.id, dossier.id, filename)
                : await ApplicationService.downloadDossier(application.id, dossier.id);
            if (activeApplicationRef.current === application.id) saveBlob(downloaded);
        } catch (downloadError) {
            if (activeApplicationRef.current !== application.id) return;
            setError(downloadError.message);
        } finally {
            if (activeApplicationRef.current === application.id) setBusy("");
        }
    };

    const refreshDraft = async () => {
        setBusy("refresh");
        setError("");
        const fingerprint = currentDraftFingerprint;
        const wasDirty = fingerprint !== savedFingerprintRef.current;
        try {
            if (savePromiseRef.current) await savePromiseRef.current;
            if (activeApplicationRef.current !== application.id) return;
            const draft = await ApplicationService.getDossierDraft(application.id);
            if (activeApplicationRef.current !== application.id) return;
            if (wasDirty || currentFingerprintRef.current !== fingerprint) setIncomingDraft({ draft });
            else installDraft(draft);
            onRetryResumeMetadata?.();
        } catch (refreshError) {
            if (activeApplicationRef.current === application.id) setError(refreshError.message);
        } finally {
            if (activeApplicationRef.current === application.id) setBusy("");
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
            <DossierTarget {...{ application, binding, resumeDrafts, resumeVersions, publishVersionId }}
                busy={Boolean(busy) || draftStatus === "loading" || draftStatus === "saving"}
                onBindingChange={(next) => { setBinding(next); setPublishVersionId(""); }}
                onPublishVersionChange={setPublishVersionId} onRefresh={refreshDraft}
                onRequest={(event) => { if (savedFingerprintRef.current !== currentFingerprintRef.current) { event.preventDefault(); setError(t("dossier.saveBeforeRequest")); } }} />
            {incomingDraft && <div className="inline-alert" role="alert"><p>{t("dossier.incomingDraft")}</p>
                <button type="button" className="button button--secondary" onClick={() => installDraft(incomingDraft.draft)}>{t("dossier.loadIncoming")}</button>
                <button type="button" className="button button--ghost" onClick={() => setIncomingDraft(null)}>{t("dossier.keepEditing")}</button>
            </div>}
            {error && <div className="inline-alert inline-alert--danger" role="alert">{error}</div>}
            {evidenceNotice && <div className="inline-alert" role="status" aria-live="polite">{evidenceNotice}</div>}
            {hasBinding && <div className={`dossier-save-status dossier-save-status--${draftStatus}`} role={draftStatusIsError ? "alert" : "status"} aria-live="polite"><span><i className={`bi ${draftStatus === "saved" ? "bi-device-ssd-fill" : draftStatusIsError ? "bi-exclamation-triangle" : "bi-device-ssd"}`} aria-hidden="true" /> {t(draftStatusKey)}</span><div>{draftStatus === "load-error" && <button type="button" className="button button--ghost" onClick={() => setDraftLoadAttempt((value) => value + 1)}>{t("dossier.retryDraftLoad")}</button>}{draftStatus === "save-error" && <button type="button" className="button button--ghost" onClick={retryDraftSave}>{t("dossier.retryDraftSave")}</button>}{draftStatus === "conflict" && <button type="button" className="button button--ghost" onClick={keepLocalDraftAfterConflict}>{t("dossier.keepLocalDraft")}</button>}{draftRevision !== null && <button type="button" className="button button--ghost" disabled={Boolean(busy) || draftStatus === "saving"} onClick={discardDraft}>{t("dossier.discardDraft")}</button>}</div></div>}
            {hasBinding && resumeMetadataStatus === "error" && <div className="inline-alert inline-alert--danger" role="alert"><span>{t("dossier.resumeMetadataError")}</span> <button type="button" className="button button--secondary" onClick={onRetryResumeMetadata}>{t("dossier.retryResumeMetadata")}</button></div>}
            {profileStatus === "error" && <div className="inline-alert inline-alert--danger" role="alert"><span>{t("dossier.profileLoadError")}</span> <button type="button" className="button button--secondary" onClick={retryProfile}>{t("dossier.retryProfile")}</button></div>}
            <DossierArtifacts application={application} busy={Boolean(busy)} onDownload={download} />
            {!hasBinding ? <div className="empty-inline"><p>{t("dossier.resumeRequired")}</p></div> : (
                <form className="dossier-form" onSubmit={publish} aria-busy={draftStatus === "loading" || draftStatus === "saving"}>
                    <fieldset className="dossier-form__workspace" disabled={Boolean(busy) || draftStatus === "loading" || draftStatus === "load-error"}>
                        <legend className="visually-hidden">{t("dossier.workspace")}</legend>
                        <DossierFields {...{ requirements, setRequirements, coverLetter, setCoverLetter, answers, setAnswers, checklist, setChecklist, updateRequirement, toggleFact, updateAnswer, updateChecklist, removeRow, resumeMetadataStatus, linkedVersion, profileStatus, eligibleFacts, evidenceSelectionDisabled }} />
                        <DossierMaterials {...{ letterOptions, setLetterOptions, emailDraft, setEmailDraft, evidenceClaims, setEvidenceClaims, generationProvenance, eligibleFacts }} defaultTemplate={linkedVersion} />
                        <button className="button button--primary" disabled={Boolean(busy) || !requirementsReady}>{busy === "publish" ? t("dossier.publishing") : t("dossier.publish")}</button>
                        <small className="dossier-disclaimer">{t("dossier.disclaimer")}</small>
                    </fieldset>
                </form>
            )}
        </section>
    );
}
