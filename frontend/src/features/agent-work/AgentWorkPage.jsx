import React, { useCallback, useState } from "react";
import { useSearchParams } from "react-router";

import { useI18n } from "../../i18n/useI18n";
import { useAgentWorkQueue } from "./useAgentWorkQueue";
import { useAgentWorkDetail } from "./useAgentWorkDetail";
import { AgentWorkDetailModal } from "./AgentWorkDetailModal";
import { AgentWorkQueue } from "./AgentWorkQueue";
import { CreateWorkDialog } from "./CreateWorkDialog";
import { WORK_KINDS } from "./agentWorkModel";
import "./agent-work.css";

export function AgentWorkPage() {
    const { t } = useI18n();
    const [searchParams, setSearchParams] = useSearchParams();
    const queue = useAgentWorkQueue(t);
    const detail = useAgentWorkDetail({ t, rememberWork: queue.rememberWork, acknowledge: queue.acknowledge });
    const { items, loading, loadingMore, hasMore, error, stateFilter, setStateFilter, loadWork } = queue;
    const { selectedWork, selectedProposal, detailLoading, detailError, loadDetail, closeDetail } = detail;
    const [isCreateOpenManual, setIsCreateOpenManual] = useState(false);
    const [manualCreateKind, setManualCreateKind] = useState(null);

    const kindParam = searchParams.get("kind");
    const actionParam = searchParams.get("action");
    const hasDeepLinkCreate = actionParam === "create"
        || WORK_KINDS.includes(kindParam)
        || Boolean(searchParams.get("job_id"))
        || Boolean(searchParams.get("application_id"));
    const isCreateOpen = isCreateOpenManual || hasDeepLinkCreate;
    const createInitialKind = manualCreateKind
        || (WORK_KINDS.includes(kindParam) ? kindParam : null)
        || (searchParams.get("application_id") ? "materials" : "discover");

    const handleCloseCreate = useCallback(() => {
        setIsCreateOpenManual(false);
        setManualCreateKind(null);
        if (hasDeepLinkCreate) {
            setSearchParams((previous) => {
                const next = new URLSearchParams(previous);
                ["action", "kind", "job_id", "application_id", "resume_id"].forEach((key) => next.delete(key));
                return next;
            });
        }
    }, [hasDeepLinkCreate, setSearchParams]);

    const handleCancelFromQueue = async (work) => {
        detail.updateWork(await queue.cancelWork(work));
    };

    const handleCreateSuccess = (createdWork) => {
        if (!createdWork) {
            loadWork();
            return;
        }
        const created = queue.acknowledge(createdWork, { prepend: true });
        if (created) loadDetail(created);
    };

    const refreshDetailAndQueue = (requestId) => {
        loadWork();
        detail.refreshDetail(requestId);
    };

    return (
        <div className="workspace-page animate-slide-up agent-work-page">
            <header className="page-header">
                <div>
                    <span className="page-eyebrow">{t("page.agentWork.eyebrow")}</span>
                    <h1 className="page-title">{t("page.agentWork.title")}</h1>
                    <p className="page-description">{t("page.agentWork.description")}</p>
                </div>
            </header>
            <section className="agent-work-disclosure-banner" aria-labelledby="agent-work-disclosure-title">
                <i className="bi bi-shield-check agent-work-disclosure-banner__icon" aria-hidden="true" />
                <div>
                    <strong id="agent-work-disclosure-title">{t("agentWork.disclosureTitle")}</strong>
                    <p>{t("agentWork.disclosureCopy")}</p>
                </div>
            </section>
            {error && (
                <div className="state-panel state-panel--danger mb-4" role="alert">
                    <p>{error}</p>
                    <button type="button" className="button button--secondary button--small" onClick={() => loadWork()}>{t("common.retry")}</button>
                </div>
            )}
            <AgentWorkQueue
                items={items}
                loading={loading}
                loadingMore={loadingMore}
                hasMore={hasMore}
                selectedState={stateFilter}
                onStateChange={setStateFilter}
                onSelectWork={loadDetail}
                onCancelWork={handleCancelFromQueue}
                onRefresh={() => loadWork()}
                onLoadMore={queue.loadMore}
                onCreateRequest={() => {
                    setManualCreateKind("discover");
                    setIsCreateOpenManual(true);
                }}
            />
            {isCreateOpen && (
                <CreateWorkDialog
                    key={`${createInitialKind}:${searchParams.get("job_id") || ""}:${searchParams.get("application_id") || ""}:${searchParams.get("resume_id") || ""}`}
                    isOpen
                    onClose={handleCloseCreate}
                    onSuccess={handleCreateSuccess}
                    initialKind={createInitialKind}
                    initialJobId={searchParams.get("job_id")}
                    initialApplicationId={searchParams.get("application_id")}
                    initialResumeId={searchParams.get("resume_id")}
                />
            )}
            {selectedWork && (
                <AgentWorkDetailModal
                    key={selectedWork.id}
                    isOpen
                    work={selectedWork}
                    proposal={selectedProposal}
                    loading={detailLoading}
                    loadError={detailError}
                    onRetry={() => loadDetail(selectedWork)}
                    onClose={closeDetail}
                    onUpdateWork={detail.updateWork}
                    onRefresh={refreshDetailAndQueue}
                />
            )}
        </div>
    );
}
