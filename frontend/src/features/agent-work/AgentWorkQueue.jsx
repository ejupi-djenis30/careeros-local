import React, { useId, useMemo, useState } from "react";
import { useI18n } from "../../i18n/useI18n";
import { AgentWorkCard } from "./AgentWorkCard";
import { filterWork, WORK_STATES } from "./agentWorkModel";

export function AgentWorkQueue({
    items = [],
    loading = false,
    selectedState = "all",
    onStateChange,
    onSelectWork,
    onCancelWork,
    onCreateRequest,
    onRefresh,
    onLoadMore,
    hasMore = false,
    loadingMore = false,
}) {
    const { t } = useI18n();
    const searchId = useId();
    const [searchQuery, setSearchQuery] = useState("");

    const filteredItems = useMemo(
        () => filterWork(items, { query: searchQuery }),
        [items, searchQuery],
    );

    return (
        <section className="agent-work-queue-section" aria-labelledby="agent-work-queue-title">
            <div className="agent-work-queue-header">
                <div>
                    <h2 id="agent-work-queue-title" className="agent-work-queue-title">
                        {t("agentWork.queueTitle")}
                    </h2>
                    <p className="agent-work-queue-subtitle">
                        {t("agentWork.queueSubtitle")}
                    </p>
                </div>
                <div className="d-flex gap-2 flex-wrap">
                    <button type="button" className="button button--secondary" onClick={onRefresh} disabled={loading || loadingMore}>
                        <i className="bi bi-arrow-clockwise" aria-hidden="true" />
                        {t("agentWork.refresh")}
                    </button>
                    <button type="button" className="button button--primary" onClick={onCreateRequest}>
                        <i className="bi bi-plus-lg" aria-hidden="true" />
                        {t("agentWork.newRequest")}
                    </button>
                </div>
            </div>

            <div className="agent-work-filter-bar">
                <div className="agent-work-state-pills" role="tablist" aria-label={t("agentWork.filterByState")}>
                    <button
                        type="button"
                        role="tab"
                        aria-selected={selectedState === "all"}
                        className={`agent-work-pill ${selectedState === "all" ? "is-active" : ""}`}
                        onClick={() => onStateChange("all")}
                    >
                        {t("agentWork.state.all")}
                    </button>
                    {WORK_STATES.map((st) => (
                        <button
                            key={st}
                            type="button"
                            role="tab"
                            aria-selected={selectedState === st}
                            className={`agent-work-pill ${selectedState === st ? "is-active" : ""}`}
                            onClick={() => onStateChange(st)}
                        >
                            {t(`agentWork.state.${st}`)}
                        </button>
                    ))}
                </div>

                <div className="agent-work-search-box">
                    <label htmlFor={searchId} className="visually-hidden">
                        {t("agentWork.searchPlaceholder")}
                    </label>
                    <div className="input-with-icon">
                        <i className="bi bi-search" aria-hidden="true" />
                        <input
                            id={searchId}
                            type="search"
                            className="form-control"
                            placeholder={t("agentWork.searchPlaceholder")}
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                        />
                    </div>
                </div>
            </div>

            {loading ? (
                <div className="state-panel" role="status">
                    <span className="desktop-boot__spinner" aria-hidden="true" />
                    <p>{t("agentWork.loadingQueue")}</p>
                </div>
            ) : items.length === 0 ? (
                <div className="state-panel agent-work-empty-state">
                    <i className="bi bi-inbox" aria-hidden="true" />
                    <h3>{t("agentWork.emptyTitle")}</h3>
                    <p>{t("agentWork.emptyCopy")}</p>
                    <button
                        type="button"
                        className="button button--primary"
                        onClick={onCreateRequest}
                    >
                        <i className="bi bi-plus-lg" aria-hidden="true" />
                        {t("agentWork.newRequest")}
                    </button>
                </div>
            ) : filteredItems.length === 0 ? (
                <div className="state-panel agent-work-empty-state">
                    <i className="bi bi-funnel" aria-hidden="true" />
                    <h3>{t("agentWork.noMatchTitle")}</h3>
                    <p>{t("agentWork.noMatchCopy")}</p>
                    <button
                        type="button"
                        className="button button--secondary"
                        onClick={() => {
                            onStateChange("all");
                            setSearchQuery("");
                        }}
                    >
                        {t("agentWork.resetFilters")}
                    </button>
                </div>
            ) : (
                <div className="agent-work-cards-grid">
                    {filteredItems.map((work) => (
                        <AgentWorkCard
                            key={work.id}
                            work={work}
                            onSelect={onSelectWork}
                            onCancel={onCancelWork}
                        />
                    ))}
                </div>
            )}
            {!loading && items.length > 0 && (
                <div className="agent-work-pagination">
                    <p aria-live="polite">{t("agentWork.loadedCount", { count: items.length })}</p>
                    {hasMore && (
                        <button type="button" className="button button--secondary" onClick={onLoadMore} disabled={loadingMore}>
                            {loadingMore ? t("agentWork.loadingMore") : t("agentWork.loadMore")}
                        </button>
                    )}
                </div>
            )}
        </section>
    );
}
