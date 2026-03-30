/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { SearchService } from '../services/search';
import { useAuth } from './AuthContext';

const SearchContext = createContext(null);

// IDs added locally (not yet confirmed by a poll) are kept for at most this many
// milliseconds before being silently dropped if the server never acknowledges them.
const PENDING_ID_TTL_MS = 30_000;

export function SearchProvider({ children }) {
    const { isLoggedIn } = useAuth();
    const [searchStatuses, setSearchStatuses] = useState({});
    const [activeProfileIds, setActiveProfileIds] = useState([]);
    const [statusHeartbeat, setStatusHeartbeat] = useState(0);
    const activeProfileIdsRef = useRef(activeProfileIds);
    // Tracks when each locally-added ID was registered so we can expire it.
    const pendingAddedAtRef = useRef({});

    useEffect(() => {
        activeProfileIdsRef.current = activeProfileIds;
    }, [activeProfileIds]);

    useEffect(() => {
        if (!isLoggedIn) {
            setSearchStatuses({});
            setActiveProfileIds([]);
            setStatusHeartbeat(0);
            pendingAddedAtRef.current = {};
            return;
        }
        let isDisposed = false;
        let timeoutId;
        let pollingInterval = 1500;
        let abortController = new AbortController();

        const scheduleNextPoll = () => {
            if (isDisposed) return;
            timeoutId = window.setTimeout(pollStatuses, pollingInterval);
        };

        const pollStatuses = async () => {
            abortController = new AbortController();
            try {
                const res = await SearchService.getAllStatuses(abortController.signal);
                if (isDisposed) return;
                setSearchStatuses(res);
                setStatusHeartbeat(prev => prev + 1);

                const runningIds = Object.entries(res)
                    .filter(([, status]) => status && ['generating', 'searching', 'analyzing'].includes(status.state))
                    .map(([id]) => String(id));

                // Merge server-confirmed running IDs with any IDs pending first server acknowledgement
                // (the brief window between addProfileId() being called and the first poll returning it).
                // IDs that the server has never seen past PENDING_ID_TTL_MS are dropped.
                setActiveProfileIds(prev => {
                    const now = Date.now();
                    const next = [...runningIds];
                    for (const id of activeProfileIdsRef.current) {
                        if (res[id]) {
                            // Server confirmed — stop tracking as pending
                            delete pendingAddedAtRef.current[id];
                        } else if (!next.includes(id)) {
                            const addedAt = pendingAddedAtRef.current[id];
                            if (addedAt !== undefined && (now - addedAt) < PENDING_ID_TTL_MS) {
                                next.push(id);
                            } else if (addedAt !== undefined) {
                                delete pendingAddedAtRef.current[id];
                                window.dispatchEvent(new CustomEvent('jh_api_error', {
                                    detail: {
                                        message: `Search ${id} did not start successfully. Please try again.`
                                    }
                                }));
                            }
                        }
                    }
                    next.sort();
                    const prevSorted = [...prev].sort();
                    if (JSON.stringify(next) === JSON.stringify(prevSorted)) return prev;
                    return next;
                });

                pollingInterval = runningIds.length > 0 ? 1500 : 15000;
            } catch (e) {
                if (e.name === 'AbortError') return;
                console.error("Failed to poll statuses:", e);
                pollingInterval = 15000;
            } finally {
                scheduleNextPoll();
            }
        };

        pollStatuses();
        return () => {
            isDisposed = true;
            window.clearTimeout(timeoutId);
            abortController.abort();
        };
    }, [isLoggedIn]);

    const addProfileId = useCallback((pid) => {
        const pidStr = String(pid);
        setActiveProfileIds(prev => {
            if (prev.includes(pidStr)) return prev;
            return [...prev, pidStr];
        });
        // Record the time this ID was locally added so the TTL check can expire it.
        if (pendingAddedAtRef.current[pidStr] === undefined) {
            pendingAddedAtRef.current[pidStr] = Date.now();
        }
    }, []);

    const removeProfileId = useCallback((pid) => {
        const pidStr = String(pid);
        delete pendingAddedAtRef.current[pidStr];
        setActiveProfileIds(prev => prev.filter(id => id !== pidStr));
    }, []);

    return (
        <SearchContext.Provider value={{
            searchStatuses,
            activeProfileIds,
            statusHeartbeat,
            addProfileId,
            removeProfileId
        }}>
            {children}
        </SearchContext.Provider>
    );
}

export function useSearchContext() {
    const context = useContext(SearchContext);
    if (!context) throw new Error('useSearchContext must be used within SearchProvider');
    return context;
}
