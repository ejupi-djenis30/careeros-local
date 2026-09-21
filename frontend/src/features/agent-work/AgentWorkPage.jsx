import React, { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";

import { useI18n } from "../../i18n/useI18n";
import { AgentWorkService } from "../../services/agentWork";
import { AgentWorkDetailModal } from "./AgentWorkDetailModal";
import { AgentWorkQueue } from "./AgentWorkQueue";
import { CreateWorkDialog } from "./CreateWorkDialog";
import { workErrorMessage, WORK_KINDS } from "./agentWorkModel";
import "./agent-work.css";

const PAGE_SIZE = 25;

function mergePage(current, next) {
    const byId = new Map(current.map((item) => [item.id, item]));
    next.forEach((item) => byId.set(item.id, item));
    return [...byId.values()];
}

export function AgentWorkPage() {
    const { t } = useI18n();
    const [searchParams, setSearchParams] = useSearchParams();
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [loadingMore, setLoadingMore] = useState(false);
    const [hasMore, setHasMore] = useState(false);
    const [error, setError] = useState("");
    const [stateFilter, setStateFilter] = useState("all");
    const listControllerRef = useRef(null);
    const listSequenceRef = useRef(0);

    const [isCreateOpenManual, setIsCreateOpenManual] = useState(false);
    const [manualCreateKind, setManualCreateKind] = useState(null);
    const [selectedWork, setSelectedWork] = useState(null);
    const [selectedProposal, setSelectedProposal] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [detailError, setDetailError] = useState("");
    const [isDetailOpen, setIsDetailOpen] = useState(false);
    const selectedIdRef = useRef(null);
    const detailControllerRef = useRef(null);
    const detailSequenceRef = useRef(0);

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

    const loadWork = useCallback(async ({ append = false, offset = 0 } = {}) => {
        listControllerRef.current?.abort();
        const controller = new AbortController();
        listControllerRef.current = controller;
        const sequence = ++listSequenceRef.current;
        if (append) setLoadingMore(true);
        else setLoading(true);
        setError("");
        const pageOffset = append ? offset : 0;
        try {
            const response = await AgentWorkService.listWork({
                offset: pageOffset,
                limit: PAGE_SIZE,
                state: stateFilter === "all" ? undefined : stateFilter,
                signal: controller.signal,
            });
            if (sequence !== listSequenceRef.current) return;
            const page = Array.isArray(response?.items) ? response.items : [];
            setItems((current) => (append ? mergePage(current, page) : page));
            setHasMore(response?.returned_count === response?.limit && page.length > 0);
        } catch (requestError) {
            if (sequence === listSequenceRef.current && requestError?.name !== "AbortError") {
                setError(workErrorMessage(requestError, t, "agentWork.error.loadQueue"));
            }
        } finally {
            if (sequence === listSequenceRef.current) {
                setLoading(false);
                setLoadingMore(false);
            }
        }
    }, [stateFilter, t]);

    useEffect(() => {
        const start = window.setTimeout(() => loadWork(), 0);
        return () => {
            window.clearTimeout(start);
            listControllerRef.current?.abort();
        };
    }, [loadWork]);

    const closeDetail = useCallback(() => {
        detailControllerRef.current?.abort();
        detailControllerRef.current = null;
        detailSequenceRef.current += 1;
        selectedIdRef.current = null;
        setIsDetailOpen(false);
        setSelectedWork(null);
        setSelectedProposal(null);
        setDetailLoading(false);
        setDetailError("");
    }, []);

    const loadDetail = useCallback(async (work) => {
        detailControllerRef.current?.abort();
        const controller = new AbortController();
        detailControllerRef.current = controller;
        const sequence = ++detailSequenceRef.current;
        selectedIdRef.current = work.id;
        setSelectedWork(work);
        setSelectedProposal(null);
        setDetailError("");
        setDetailLoading(true);
        setIsDetailOpen(true);
        try {
            const detail = await AgentWorkService.getWork(work.id, { signal: controller.signal });
            if (
                sequence !== detailSequenceRef.current
                || selectedIdRef.current !== work.id
                || controller.signal.aborted
            ) return;
            setSelectedWork(detail);
            setSelectedProposal(detail.proposal || null);
        } catch (requestError) {
            if (sequence === detailSequenceRef.current && requestError?.name !== "AbortError") {
                setDetailError(workErrorMessage(requestError, t, "agentWork.error.loadDetail"));
            }
        } finally {
            if (sequence === detailSequenceRef.current) setDetailLoading(false);
        }
    }, [t]);

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
        try {
            const updated = await AgentWorkService.cancelWork(work.id, {
                expected_revision: work.revision,
            });
            setItems((current) => current.map((item) => (item.id === updated.id ? updated : item)));
        } catch (requestError) {
            setError(workErrorMessage(requestError, t, "agentWork.error.cancelFailed"));
        }
    };

    const handleUpdateWork = (updatedWork) => {
        if (!updatedWork) return;
        if (selectedIdRef.current === updatedWork.id) setSelectedWork(updatedWork);
        setItems((current) => {
            if (stateFilter !== "all" && updatedWork.state !== stateFilter) {
                return current.filter((item) => item.id !== updatedWork.id);
            }
            return current.map((item) => (item.id === updatedWork.id ? updatedWork : item));
        });
    };

    const handleCreateSuccess = (createdWork) => {
        if (!createdWork) {
            loadWork();
            return;
        }
        if (stateFilter === "all" || stateFilter === createdWork.state) {
            setItems((current) => mergePage([createdWork], current));
        }
        loadDetail(createdWork);
    };

    const refreshDetailAndQueue = (requestId) => {
        loadWork();
        if (requestId && selectedIdRef.current === requestId && selectedWork) loadDetail(selectedWork);
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
                onLoadMore={() => loadWork({ append: true, offset: items.length })}
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
            {isDetailOpen && selectedWork && (
                <AgentWorkDetailModal
                    key={selectedWork.id}
                    isOpen={isDetailOpen}
                    work={selectedWork}
                    proposal={selectedProposal}
                    loading={detailLoading}
                    loadError={detailError}
                    onRetry={() => loadDetail(selectedWork)}
                    onClose={closeDetail}
                    onUpdateWork={handleUpdateWork}
                    onRefresh={refreshDetailAndQueue}
                />
            )}
        </div>
    );
}
