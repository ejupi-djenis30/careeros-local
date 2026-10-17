import { useCallback, useEffect, useRef, useState } from "react";
import { AgentWorkService } from "../../services/agentWork";
import { workErrorMessage } from "./agentWorkModel";

const PAGE_SIZE = 25;
const matches = (work, filter) => filter === "all" || work.state === filter;

export function useAgentWorkQueue(t) {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [loadingMore, setLoadingMore] = useState(false);
    const [hasMore, setHasMore] = useState(false);
    const [error, setError] = useState("");
    const [stateFilter, setFilter] = useState("all");
    const filterRef = useRef("all");
    const projectionSequence = useRef(0);
    const mounted = useRef(true);
    const request = useRef({ controller: null, sequence: 0 });
    const known = useRef(new Map());
    const acknowledgements = useRef(new Map());
    const acknowledgementSequence = useRef(0);
    const pagination = useRef({ cursor: 0, dirty: false, hasMore: false });
    const cancellations = useRef(new Map());

    useEffect(() => {
        mounted.current = true;
        const activeRequest = request.current;
        const pending = cancellations.current;
        return () => {
            mounted.current = false;
            activeRequest.controller?.abort();
            activeRequest.sequence += 1;
            pending.forEach((operation) => operation.controller.abort());
            pending.clear();
        };
    }, []);

    const rememberWork = useCallback((work) => {
        if (!work) return null;
        const previous = known.current.get(work.id);
        if (previous && previous.revision > work.revision) return previous;
        const next = { ...previous, ...work };
        known.current.set(work.id, next);
        return next;
    }, []);

    const project = useCallback((rows) => {
        const byId = new Map(rows.map((work) => [work.id, rememberWork(work)]));
        return [...byId.values()].filter((work) => matches(work, filterRef.current));
    }, [rememberWork]);

    const acknowledge = useCallback((work, { prepend = false } = {}) => {
        if (!mounted.current || !work) return null;
        const next = rememberWork(work);
        const previous = acknowledgements.current.get(next.id);
        if (!previous || previous.revision < next.revision) {
            acknowledgementSequence.current += 1;
            pagination.current.dirty = true;
        }
        acknowledgements.current.set(next.id, next);
        setItems((current) => project(prepend ? [next, ...current] : [...current, next]));
        return next;
    }, [project, rememberWork]);

    const setStateFilter = useCallback((next) => {
        if (filterRef.current === next) return;
        filterRef.current = next;
        projectionSequence.current += 1;
        pagination.current = { cursor: 0, dirty: false, hasMore: false };
        setHasMore(false);
        request.current.controller?.abort();
        request.current.sequence += 1;
        setItems((current) => current.filter((work) => matches(work, next)));
        setLoading(true);
        setLoadingMore(false);
        setError("");
        setFilter(next);
    }, []);

    const loadWork = useCallback(async ({ append = false, offset = 0, preserve = false } = {}) => {
        if (!mounted.current || filterRef.current !== stateFilter) return false;
        request.current.controller?.abort();
        const controller = new AbortController();
        request.current.controller = controller;
        const sequence = ++request.current.sequence;
        const startedAcknowledgement = acknowledgementSequence.current;
        const pageOffset = append ? offset : 0;
        const isCurrent = () => mounted.current && !controller.signal.aborted
            && request.current.sequence === sequence && filterRef.current === stateFilter;
        if (append) setLoadingMore(true);
        else setLoading(true);
        setError("");
        try {
            const response = await AgentWorkService.listWork({
                offset: pageOffset, limit: PAGE_SIZE,
                state: stateFilter === "all" ? undefined : stateFilter,
                signal: controller.signal,
            });
            if (!isCurrent()) return;
            const rawPage = Array.isArray(response?.items) ? response.items : [];
            const stale = rawPage.some((work) => known.current.get(work.id)?.revision > work.revision);
            const page = rawPage.map(rememberWork);
            setItems((current) => project([
                ...(append || preserve ? current : []), ...page, ...acknowledgements.current.values(),
            ]));
            const more = response?.returned_count === response?.limit && page.length > 0;
            pagination.current = {
                cursor: pageOffset + rawPage.length, hasMore: more,
                dirty: stale || startedAcknowledgement !== acknowledgementSequence.current,
            };
            setHasMore(more);
            return true;
        } catch (reason) {
            if (isCurrent() && reason?.name !== "AbortError") {
                setError(workErrorMessage(reason, t, "agentWork.error.loadQueue"));
            }
        } finally {
            if (isCurrent()) {
                request.current.controller = null;
                setLoading(false);
                setLoadingMore(false);
            }
        }
    }, [project, rememberWork, stateFilter, t]);

    useEffect(() => {
        const activeRequest = request.current;
        const start = window.setTimeout(() => void loadWork(), 0);
        return () => {
            window.clearTimeout(start);
            activeRequest.controller?.abort();
        };
    }, [loadWork]);

    const loadMore = useCallback(async () => {
        const projection = projectionSequence.current;
        const isCurrent = () => mounted.current && projectionSequence.current === projection;
        if (pagination.current.dirty) {
            const previousCursor = pagination.current.cursor;
            if (!await loadWork({ preserve: true }) || !isCurrent()) return;
            const loadedPages = Math.max(1, Math.ceil(previousCursor / PAGE_SIZE));
            for (let page = 1; page < loadedPages && !pagination.current.dirty
                && pagination.current.hasMore; page += 1) {
                const cursor = pagination.current.cursor;
                if (!await loadWork({ append: true, offset: cursor }) || !isCurrent()
                    || pagination.current.cursor <= cursor) return;
            }
        }
        if (isCurrent() && !pagination.current.dirty && pagination.current.hasMore) {
            return loadWork({ append: true, offset: pagination.current.cursor });
        }
    }, [loadWork]);

    const cancelWork = useCallback((work) => {
        const existing = cancellations.current.get(work.id);
        if (existing) return existing.promise;
        const operation = { controller: new AbortController(), promise: null };
        const projection = projectionSequence.current;
        cancellations.current.set(work.id, operation);
        setError("");
        operation.promise = (async () => {
            try {
                const result = await AgentWorkService.cancelWork(work.id, {
                    expected_revision: work.revision,
                }, { signal: operation.controller.signal });
                if (mounted.current && !operation.controller.signal.aborted) return result;
            } catch (reason) {
                if (mounted.current && !operation.controller.signal.aborted
                    && projectionSequence.current === projection && reason?.name !== "AbortError") {
                    setError(workErrorMessage(reason, t, "agentWork.error.cancelFailed"));
                }
            } finally {
                if (cancellations.current.get(work.id) === operation) cancellations.current.delete(work.id);
            }
        })();
        return operation.promise;
    }, [t]);

    return { items, loading, loadingMore, hasMore, error, stateFilter, setStateFilter, loadWork, loadMore, rememberWork, acknowledge, cancelWork };
}
