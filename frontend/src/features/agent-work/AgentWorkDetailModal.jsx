import React, { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useI18n } from "../../i18n/useI18n";
import { CopyButton } from "../agent-access/AgentAccessShared";
import { canCancel, formatCopyablePrompt, workErrorMessage } from "./agentWorkModel";
import { ProposalReview } from "./ProposalReview";
import { AgentWorkService } from "../../services/agentWork";
import { useAgentModalIsolation } from "./useAgentModalIsolation";
import { InternalLink } from "../../components/InternalLink";

export function AgentWorkDetailModal({
    isOpen,
    work,
    proposal,
    loading = false,
    loadError = "",
    onRetry,
    onClose,
    onUpdateWork,
    onRefresh,
}) {
    const { t, language } = useI18n();
    const titleId = useId();
    const dialogRef = useRef(null);
    const closeButtonRef = useRef(null);
    const actionSequenceRef = useRef(0);

    const [canceling, setCanceling] = useState(false);
    const [accepting, setAccepting] = useState(false);
    const [rejecting, setRejecting] = useState(false);
    const [actionError, setActionError] = useState("");
    const [copyNotice, setCopyNotice] = useState("");

    const locale = language === "it" ? "it-IT" : "en-GB";
    const busy = canceling || accepting || rejecting;
    useAgentModalIsolation({
        isOpen,
        dialogRef,
        initialFocusRef: closeButtonRef,
        onRequestClose: onClose,
        closeBlocked: busy,
    });
    useEffect(() => () => {
        actionSequenceRef.current += 1;
    }, []);

    if (!isOpen || !work) return null;

    const copyablePrompt = formatCopyablePrompt(work);
    const stateClass = `agent-work-state--${work.state}`;
    const createdDate = work.created_at ? new Date(work.created_at).toLocaleString(locale) : "—";
    const expiresDate = work.expires_at ? new Date(work.expires_at).toLocaleString(locale) : "—";

    const handleCancel = async () => {
        if (canceling) return;
        setCanceling(true);
        setActionError("");
        const sequence = ++actionSequenceRef.current;
        try {
            const updated = await AgentWorkService.cancelWork(work.id, {
                expected_revision: work.revision,
            });
            if (sequence === actionSequenceRef.current) onUpdateWork(updated);
        } catch (error) {
            if (sequence === actionSequenceRef.current) {
                setActionError(workErrorMessage(error, t, "agentWork.error.cancelFailed"));
                if (onRefresh) onRefresh(work.id);
            }
        } finally {
            if (sequence === actionSequenceRef.current) setCanceling(false);
        }
    };

    const handleAccept = async () => {
        if (accepting) return;
        setAccepting(true);
        setActionError("");
        const sequence = ++actionSequenceRef.current;
        try {
            const res = await AgentWorkService.acceptWork(work.id, {
                expected_revision: work.revision,
                expected_target_revisions: work.input_revisions || {},
            });
            const updated = {
                ...work,
                state: "accepted",
                revision: work.revision + 1,
                accepted_receipt: res,
            };
            if (sequence === actionSequenceRef.current) onUpdateWork(updated);
        } catch (error) {
            if (sequence === actionSequenceRef.current) {
                setActionError(workErrorMessage(error, t, "agentWork.error.acceptFailed"));
                if (onRefresh) onRefresh(work.id);
            }
        } finally {
            if (sequence === actionSequenceRef.current) setAccepting(false);
        }
    };

    const handleReject = async () => {
        if (rejecting) return;
        setRejecting(true);
        setActionError("");
        const sequence = ++actionSequenceRef.current;
        try {
            const updated = await AgentWorkService.rejectWork(work.id, {
                expected_revision: work.revision,
            });
            if (sequence === actionSequenceRef.current) onUpdateWork(updated);
        } catch (error) {
            if (sequence === actionSequenceRef.current) {
                setActionError(workErrorMessage(error, t, "agentWork.error.rejectFailed"));
                if (onRefresh) onRefresh(work.id);
            }
        } finally {
            if (sequence === actionSequenceRef.current) setRejecting(false);
        }
    };

    return createPortal(
        <div
            className="agent-work-modal-backdrop"
            onClick={(e) => {
                if (e.target === e.currentTarget && !busy) onClose();
            }}
        >
            <div
                ref={dialogRef}
                className="agent-work-modal-content surface-section agent-work-detail-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
                tabIndex="-1"
            >
                <div className="agent-work-modal-header">
                    <div>
                        <div className="d-flex align-items-center gap-2 mb-1">
                            <span className="agent-work-kind-badge">
                                {t(`agentWork.kind.${work.work_kind}`)}
                            </span>
                            <span className={`agent-work-state-badge ${stateClass}`}>
                                {t(`agentWork.state.${work.state}`)}
                            </span>
                            <span className="agent-work-revision">
                                {t("agentWork.revisionNumber", { revision: work.revision })}
                            </span>
                        </div>
                        <h2 id={titleId} className="agent-work-modal-title">
                            {work.instruction ? work.instruction.slice(0, 80) : t("agentWork.requestDetail")}
                        </h2>
                    </div>
                    <button
                        ref={closeButtonRef}
                        type="button"
                        className="icon-button"
                        aria-label={t("common.close")}
                        onClick={onClose}
                        disabled={busy}
                    >
                        <i className="bi bi-x-lg" aria-hidden="true" />
                    </button>
                </div>

                <div className="agent-work-detail-body">
                    {actionError && work.state !== "returned" && (
                        <div className="agent-inline-error" role="alert">{actionError}</div>
                    )}
                    {/* Metadata strip */}
                    <div className="agent-work-metadata-strip">
                        <div>
                            <span className="meta-label">{t("agentWork.requestId")}</span>
                            <code>{work.id}</code>
                        </div>
                        <div>
                            <span className="meta-label">{t("agentWork.created")}</span>
                            <span>{createdDate}</span>
                        </div>
                        <div>
                            <span className="meta-label">{t("agentWork.expires")}</span>
                            <span>{expiresDate}</span>
                        </div>
                    </div>

                    {/* Instructions card */}
                    <div className="agent-work-instructions-card">
                        <span className="section-kicker">{t("agentWork.instructions")}</span>
                        <p>{work.instruction || t("agentWork.noInstructions")}</p>
                    </div>

                    {/* Status-specific body */}
                    {work.state === "queued" && (
                        <div className="agent-work-queued-panel state-panel">
                            <i className="bi bi-hourglass-top text-info" aria-hidden="true" />
                            <h3>{t("agentWork.waitingForAgentTitle")}</h3>
                            <p>{t("agentWork.waitingForAgentCopy")}</p>

                            <div className="agent-work-prompt-box">
                                <div className="prompt-header">
                                    <span className="prompt-label">{t("agentWork.copyPromptLabel")}</span>
                                    <CopyButton
                                        value={copyablePrompt}
                                        label={t("agentWork.copyPrompt")}
                                        copiedLabel={t("agentAccess.copied")}
                                        onResult={(ok) => setCopyNotice(ok ? t("agentAccess.copySuccess") : t("agentAccess.copyFailed"))}
                                    />
                                </div>
                                <pre tabIndex="0"><code>{copyablePrompt}</code></pre>
                                <small className="prompt-privacy-note">
                                    <i className="bi bi-shield-lock me-1" aria-hidden="true" />
                                    {t("agentWork.promptPrivacyNotice")}
                                </small>
                            </div>

                            {copyNotice && (
                                <p className="agent-copy-status" role="status">{copyNotice}</p>
                            )}

                            {canCancel(work) && (
                                <div className="mt-4">
                                    <button
                                        type="button"
                                        className="button button--secondary text-danger"
                                        onClick={handleCancel}
                                        disabled={canceling}
                                    >
                                        <i className="bi bi-x-circle me-1" aria-hidden="true" />
                                        {canceling ? t("agentWork.canceling") : t("agentWork.cancelRequest")}
                                    </button>
                                </div>
                            )}
                        </div>
                    )}

                    {work.state === "returned" && loading && (
                        <div className="state-panel" role="status">{t("agentWork.loadingDetail")}</div>
                    )}
                    {work.state === "returned" && loadError && !loading && (
                        <div className="state-panel state-panel--danger" role="alert">
                            <p>{loadError}</p>
                            <button type="button" className="button button--secondary" onClick={onRetry}>{t("common.retry")}</button>
                        </div>
                    )}
                    {work.state === "returned" && !loading && !loadError && (
                        <ProposalReview
                            work={work}
                            proposal={proposal}
                            onAccept={handleAccept}
                            onReject={handleReject}
                            accepting={accepting}
                            rejecting={rejecting}
                            errorMessage={actionError}
                        />
                    )}

                    {work.state === "accepted" && (
                        <div className="agent-work-terminal-panel state-panel state-panel--success">
                            <i className="bi bi-check-circle-fill text-success" aria-hidden="true" />
                            <h3>{t("agentWork.acceptedTitle")}</h3>
                            <p>{t("agentWork.acceptedCopy")}</p>
                            {work.work_kind === "materials" && work.target_application_id && (
                                <InternalLink
                                    to={`/applications?applicationId=${encodeURIComponent(work.target_application_id)}`}
                                    className="button button--primary mt-3"
                                    onClick={onClose}
                                >
                                    <i className="bi bi-folder2-open" aria-hidden="true" />
                                    {t("agentWork.openAcceptedMaterials")}
                                </InternalLink>
                            )}
                            {work.accepted_receipt && (
                                <details className="mt-3">
                                    <summary>{t("agentWork.viewReceipt")}</summary>
                                    <pre tabIndex="0"><code>{JSON.stringify(work.accepted_receipt, null, 2)}</code></pre>
                                </details>
                            )}
                        </div>
                    )}

                    {work.state === "rejected" && (
                        <div className="agent-work-terminal-panel state-panel">
                            <i className="bi bi-x-circle text-danger" aria-hidden="true" />
                            <h3>{t("agentWork.rejectedTitle")}</h3>
                            <p>{t("agentWork.rejectedCopy")}</p>
                        </div>
                    )}

                    {work.state === "canceled" && (
                        <div className="agent-work-terminal-panel state-panel">
                            <i className="bi bi-slash-circle text-muted" aria-hidden="true" />
                            <h3>{t("agentWork.canceledTitle")}</h3>
                            <p>{t("agentWork.canceledCopy")}</p>
                        </div>
                    )}

                    {work.state === "expired" && (
                        <div className="agent-work-terminal-panel state-panel">
                            <i className="bi bi-clock-history text-muted" aria-hidden="true" />
                            <h3>{t("agentWork.expiredTitle")}</h3>
                            <p>{t("agentWork.expiredCopy")}</p>
                        </div>
                    )}
                </div>

                <div className="agent-work-modal-footer">
                    <button
                        type="button"
                        className="button button--secondary"
                        onClick={onClose}
                        disabled={busy}
                    >
                        {t("common.close")}
                    </button>
                </div>
            </div>
        </div>,
        document.body,
    );
}
