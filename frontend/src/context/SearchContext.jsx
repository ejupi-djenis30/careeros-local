/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { SearchService } from '../services/search';
import { useAuth } from './AuthContext';
import { CAREEROS_API_ERROR_EVENT } from '../lib/events';

const SearchContext = createContext(null);

// IDs added locally (not yet confirmed by a poll) are kept for at most this many
// milliseconds before being silently dropped if the server never acknowledges them.
const PENDING_ID_TTL_MS = 30_000;

function areArraysEqual(left, right) {
    if (left.length !== right.length) {
        return false;
    }

    return left.every((value, index) => value === right[index]);
}

function areStatusValuesEqual(left, right) {
    if (Object.is(left, right)) {
        return true;
    }

    if (!left || !right || typeof left !== 'object' || typeof right !== 'object') {
        return false;
    }

    const leftKeys = Object.keys(left);
    const rightKeys = Object.keys(right);
    if (leftKeys.length !== rightKeys.length) {
        return false;
    }

    return leftKeys.every(key => {
        const leftValue = left[key];
        const rightValue = right[key];

        if (Object.is(leftValue, rightValue)) {
            return true;
        }

        if (
            leftValue &&
            rightValue &&
            typeof leftValue === 'object' &&
            typeof rightValue === 'object'
        ) {
            return JSON.stringify(leftValue) === JSON.stringify(rightValue);
        }

        return false;
    });
}

function haveStatusesChanged(previousStatuses, nextStatuses) {
    const previousIds = Object.keys(previousStatuses);
    const nextIds = Object.keys(nextStatuses);

    if (previousIds.length !== nextIds.length) {
        return true;
    }

    return nextIds.some(id => !areStatusValuesEqual(previousStatuses[id], nextStatuses[id]));
}

export function SearchProvider({ children }) {
    const { isLoggedIn } = useAuth();
    const [searchStatuses, setSearchStatuses] = useState({});
    const [activeProfileIds, setActiveProfileIds] = useState([]);
    const [statusHeartbeat, setStatusHeartbeat] = useState(0);
    const activeProfileIdsRef = useRef(activeProfileIds);
    // Tracks when each locally-added ID was registered so we can expire it.
    const pendingAddedAtRef = useRef({});
    // Tracks the last polled statuses so consumers only wake up on real changes.
    const lastStatusesRef = useRef({});

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
                // Only wake up consumers when the status data actually changed.
                if (haveStatusesChanged(lastStatusesRef.current, res)) {
                    lastStatusesRef.current = res;
                    setStatusHeartbeat(prev => prev + 1);
                }

                const runningIds = Object.entries(res)
                    .filter(([, status]) => status && ['reserved', 'generating', 'searching', 'analyzing'].includes(status.state))
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
                                window.dispatchEvent(new CustomEvent(CAREEROS_API_ERROR_EVENT, {
                                    detail: {
                                        message: `Search ${id} did not start successfully. Please try again.`
                                    }
                                }));
                            }
                        }
                    }
                    next.sort();
                    const prevSorted = [...prev].sort();
                    if (areArraysEqual(next, prevSorted)) return prev;
                    return next;
                });

                pollingInterval = runningIds.length > 0 ? 1500 : 15000;
            } catch (e) {
                if (e.name === 'AbortError') return;
                console.error("Failed to poll statuses:", e);
                window.dispatchEvent(new CustomEvent(CAREEROS_API_ERROR_EVENT, {
                    detail: {
                        message: 'Live search status updates are temporarily unavailable. Retrying...'
                    }
                }));
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
            lastStatusesRef.current = {};
        };
    }, [isLoggedIn]);

    const addProfileId = useCallback((pid) => {
        const pidStr = String(pid);
        setActiveProfileIds(prev => {
            if (prev.includes(pidStr)) return prev;
            // Update ref inside the setState callback so it is atomic with the state change.
            if (pendingAddedAtRef.current[pidStr] === undefined) {
                pendingAddedAtRef.current[pidStr] = Date.now();
            }
            return [...prev, pidStr];
        });
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
