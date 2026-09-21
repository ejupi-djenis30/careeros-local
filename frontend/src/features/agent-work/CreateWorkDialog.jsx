import React, { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router";

import { useI18n } from "../../i18n/useI18n";
import { AgentWorkService } from "../../services/agentWork";
import { ApplicationService } from "../../services/applications";
import { AutomationService } from "../../services/automation";
import { ResumeService } from "../../services/resumes";
import { grantState } from "../agent-access/agentAccessModel";
import { workErrorMessage, WORK_KINDS } from "./agentWorkModel";
import { useAgentModalIsolation } from "./useAgentModalIsolation";

function hasWorkspaceScopes(grant) {
    const scopes = grant?.scopes || [];
    return scopes.includes("context:read") && scopes.includes("proposals:write");
}

function applicationLabel(application) {
    const snapshot = application.job_snapshot || {};
    const title = application.title || snapshot.title || application.id;
    const company = application.company || snapshot.company;
    return company ? `${title} · ${company}` : title;
}

export function CreateWorkDialog({
    isOpen,
    onClose,
    onSuccess,
    initialKind = "discover",
    initialJobId = null,
    initialApplicationId = null,
    initialResumeId = null,
}) {
    const { t } = useI18n();
    const titleId = useId();
    const dialogRef = useRef(null);
    const instructionsInputRef = useRef(null);
    const submitControllerRef = useRef(null);
    const submitSequenceRef = useRef(0);
    const openRef = useRef(isOpen);

    const initialWorkKind = WORK_KINDS.includes(initialKind) ? initialKind : "discover";
    const [kind, setKind] = useState(initialWorkKind);
    const [grantId, setGrantId] = useState("");
    const [instructions, setInstructions] = useState("");
    const [targetJobId, setTargetJobId] = useState(initialJobId ? String(initialJobId) : "");
    const [targetApplicationId, setTargetApplicationId] = useState(initialApplicationId || "");
    const [targetResumeId, setTargetResumeId] = useState(initialResumeId || "");
    const [grants, setGrants] = useState([]);
    const [applications, setApplications] = useState([]);
    const [resumes, setResumes] = useState([]);
    const [loadingGrants, setLoadingGrants] = useState(true);
    const [loadingTargets, setLoadingTargets] = useState(initialWorkKind === "materials");
    const [grantError, setGrantError] = useState("");
    const [targetError, setTargetError] = useState("");
    const [grantAttempt, setGrantAttempt] = useState(0);
    const [targetAttempt, setTargetAttempt] = useState(0);
    const [submitting, setSubmitting] = useState(false);
    const [errorMessage, setErrorMessage] = useState("");

    useEffect(() => {
        openRef.current = isOpen;
        return () => {
            submitControllerRef.current?.abort();
            submitControllerRef.current = null;
            submitSequenceRef.current += 1;
            openRef.current = false;
        };
    }, [isOpen]);

    useEffect(() => {
        if (!isOpen) return undefined;
        let active = true;
        const controller = new AbortController();
        AutomationService.listGrants({ signal: controller.signal })
            .then((items) => {
                if (!active) return;
                const now = Date.now();
                const eligible = (Array.isArray(items) ? items : []).filter(
                    (grant) => grantState(grant, now) === "active" && hasWorkspaceScopes(grant),
                );
                setGrants(eligible);
                setGrantId((current) => (
                    eligible.some((grant) => grant.id === current) ? current : eligible[0]?.id || ""
                ));
            })
            .catch((error) => {
                if (active && error?.name !== "AbortError") {
                    setGrants([]);
                    setGrantId("");
                    setGrantError(workErrorMessage(error, t, "agentWork.error.loadGrants"));
                }
            })
            .finally(() => {
                if (active) setLoadingGrants(false);
            });
        return () => {
            active = false;
            controller.abort();
        };
    }, [grantAttempt, isOpen, t]);

    useEffect(() => {
        if (!isOpen || kind !== "materials") return undefined;
        let active = true;
        const controller = new AbortController();
        Promise.all([
            ApplicationService.list({ signal: controller.signal, suppressGlobalError: true }),
            ResumeService.list({ signal: controller.signal, suppressGlobalError: true }),
        ])
            .then(([applicationItems, resumeItems]) => {
                if (!active) return;
                setApplications(Array.isArray(applicationItems) ? applicationItems : []);
                setResumes(Array.isArray(resumeItems) ? resumeItems : []);
            })
            .catch((error) => {
                if (active && error?.name !== "AbortError") {
                    setApplications([]);
                    setResumes([]);
                    setTargetError(workErrorMessage(error, t, "agentWork.error.loadTargets"));
                }
            })
            .finally(() => {
                if (active) setLoadingTargets(false);
            });
        return () => {
            active = false;
            controller.abort();
        };
    }, [isOpen, kind, targetAttempt, t]);

    const requestClose = () => {
        if (!submitting) onClose();
    };
    useAgentModalIsolation({
        isOpen,
        dialogRef,
        initialFocusRef: instructionsInputRef,
        onRequestClose: requestClose,
        closeBlocked: submitting,
    });

    const selectedGrant = useMemo(
        () => grants.find((grant) => grant.id === grantId) || null,
        [grantId, grants],
    );
    const validJobTarget = kind !== "analyze"
        || (Number.isInteger(Number(targetJobId)) && Number(targetJobId) > 0);
    const validMaterialTargets = kind !== "materials"
        || (Boolean(targetApplicationId) && Boolean(targetResumeId));
    const canSubmit = Boolean(
        selectedGrant
        && instructions.trim()
        && validJobTarget
        && validMaterialTargets
        && !loadingGrants
        && !loadingTargets
        && !grantError
        && !targetError,
    );

    const handleSubmit = async (event) => {
        event.preventDefault();
        if (submitting || !canSubmit) return;
        const controller = new AbortController();
        submitControllerRef.current = controller;
        const sequence = ++submitSequenceRef.current;
        setSubmitting(true);
        setErrorMessage("");
        const payload = {
            work_kind: kind,
            grant_id: grantId,
            instruction: instructions.trim(),
        };
        if (kind === "analyze") payload.target_job_id = Number(targetJobId);
        if (kind === "materials") {
            payload.target_application_id = targetApplicationId;
            payload.target_resume_id = targetResumeId;
        }
        try {
            const created = await AgentWorkService.createWork(payload, { signal: controller.signal });
            if (sequence !== submitSequenceRef.current || !openRef.current) return;
            onSuccess(created);
            onClose();
        } catch (error) {
            if (sequence === submitSequenceRef.current && error?.name !== "AbortError") {
                setErrorMessage(workErrorMessage(error, t, "agentWork.error.createFailed"));
            }
        } finally {
            if (sequence === submitSequenceRef.current) {
                submitControllerRef.current = null;
                setSubmitting(false);
            }
        }
    };

    if (!isOpen) return null;
    return createPortal(
        <div className="agent-work-modal-backdrop" onClick={(event) => {
            if (event.target === event.currentTarget) requestClose();
        }}>
            <div ref={dialogRef} className="agent-work-modal-content surface-section" role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex="-1">
                <header className="agent-work-modal-header">
                    <div>
                        <span className="section-kicker">{t("agentWork.modalKicker")}</span>
                        <h2 id={titleId}>{t("agentWork.createTitle")}</h2>
                    </div>
                    <button type="button" className="icon-button" aria-label={t("common.close")} onClick={requestClose} disabled={submitting}>
                        <i className="bi bi-x-lg" aria-hidden="true" />
                    </button>
                </header>
                <form onSubmit={handleSubmit} className="agent-work-form">
                    <fieldset className="agent-work-kind-picker" disabled={submitting}>
                        <legend>{t("agentWork.selectKind")}</legend>
                        <div className="agent-work-kind-grid">
                            {WORK_KINDS.map((workKind) => (
                                <label key={workKind} className={`agent-work-kind-card ${kind === workKind ? "is-selected" : ""}`}>
                                    <input type="radio" name="workKind" value={workKind} checked={kind === workKind} onChange={() => {
                                        setKind(workKind);
                                        if (workKind === "materials") {
                                            setLoadingTargets(true);
                                            setTargetError("");
                                        }
                                    }} />
                                    <span><strong>{t(`agentWork.kind.${workKind}`)}</strong><small>{t(`agentWork.kind.${workKind}.description`)}</small></span>
                                </label>
                            ))}
                        </div>
                    </fieldset>
                    <div className="field-stack">
                        <span>{t("agentWork.boundGrant")}</span>
                        {loadingGrants && <p role="status">{t("agentWork.loadingGrants")}</p>}
                        {grantError && (
                            <div className="agent-work-warning-banner" role="alert">
                                <p>{grantError}</p>
                                <button type="button" className="button button--secondary button--small" onClick={() => {
                                    setLoadingGrants(true);
                                    setGrantError("");
                                    setGrantAttempt((value) => value + 1);
                                }}>{t("common.retry")}</button>
                            </div>
                        )}
                        {!loadingGrants && !grantError && grants.length === 0 && (
                            <div className="agent-work-warning-banner" role="alert">
                                <p>{t("agentWork.noActiveGrantsCopy")}</p>
                                <Link to="/agent-access" className="button button--secondary button--small" onClick={requestClose}>{t("agentWork.goToAgentAccess")}</Link>
                            </div>
                        )}
                        {!loadingGrants && !grantError && grants.length > 0 && (
                            <select className="form-select" value={grantId} onChange={(event) => setGrantId(event.target.value)} disabled={submitting} aria-label={t("agentWork.boundGrant")} required>
                                {grants.map((grant) => <option key={grant.id} value={grant.id}>{grant.label}</option>)}
                            </select>
                        )}
                    </div>
                    {kind === "analyze" && (
                        <label className="field-stack">
                            <span>{t("agentWork.targetJob")}</span>
                            <input className="form-control" type="number" min="1" step="1" value={targetJobId} onChange={(event) => setTargetJobId(event.target.value)} disabled={submitting} required />
                            <small>{t("agentWork.targetJobHelp")}</small>
                        </label>
                    )}
                    {kind === "materials" && (
                        <fieldset className="agent-work-material-targets" disabled={submitting || loadingTargets}>
                            <legend>{t("agentWork.materialTargets")}</legend>
                            {loadingTargets && <p role="status">{t("agentWork.loadingTargets")}</p>}
                            {targetError && (
                                <div className="agent-work-warning-banner" role="alert">
                                    <p>{targetError}</p>
                                    <button type="button" className="button button--secondary button--small" onClick={() => {
                                        setLoadingTargets(true);
                                        setTargetError("");
                                        setTargetAttempt((value) => value + 1);
                                    }}>{t("common.retry")}</button>
                                </div>
                            )}
                            {!targetError && !loadingTargets && (
                                <>
                                    <label className="field-stack">
                                        <span>{t("agentWork.targetApplication")}</span>
                                        <select className="form-select" value={targetApplicationId} onChange={(event) => setTargetApplicationId(event.target.value)} required>
                                            <option value="">{t("agentWork.selectApplication")}</option>
                                            {targetApplicationId && !applications.some((item) => item.id === targetApplicationId) && <option value={targetApplicationId}>{targetApplicationId}</option>}
                                            {applications.map((application) => <option key={application.id} value={application.id}>{applicationLabel(application)}</option>)}
                                        </select>
                                    </label>
                                    <label className="field-stack">
                                        <span>{t("agentWork.targetResume")}</span>
                                        <select className="form-select" value={targetResumeId} onChange={(event) => setTargetResumeId(event.target.value)} required>
                                            <option value="">{t("agentWork.selectResume")}</option>
                                            {targetResumeId && !resumes.some((item) => item.id === targetResumeId) && <option value={targetResumeId}>{targetResumeId}</option>}
                                            {resumes.map((resume) => <option key={resume.id} value={resume.id}>{resume.title || resume.id}</option>)}
                                        </select>
                                    </label>
                                </>
                            )}
                        </fieldset>
                    )}
                    <label className="field-stack">
                        <span>{t("agentWork.instructions")}</span>
                        <textarea ref={instructionsInputRef} className="form-control" rows="4" maxLength="4000" value={instructions} onChange={(event) => setInstructions(event.target.value)} disabled={submitting} required />
                        <small>{instructions.length} / 4000</small>
                    </label>
                    {errorMessage && <div className="agent-inline-error" role="alert">{errorMessage}</div>}
                    <div className="agent-work-modal-actions">
                        <button type="button" className="button button--secondary" onClick={requestClose} disabled={submitting}>{t("common.cancel")}</button>
                        <button type="submit" className="button button--primary" disabled={submitting || !canSubmit}>{submitting ? t("agentWork.creating") : t("agentWork.create")}</button>
                    </div>
                </form>
            </div>
        </div>,
        document.body,
    );
}
