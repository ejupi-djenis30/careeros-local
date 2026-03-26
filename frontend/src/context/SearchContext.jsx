/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { SearchService } from '../services/search';
import { useAuth } from './AuthContext';

const SearchContext = createContext(null);

export function SearchProvider({ children }) {
    const { isLoggedIn } = useAuth();
    const [searchStatuses, setSearchStatuses] = useState({});
    const [activeProfileIds, setActiveProfileIds] = useState([]);
    const activeProfileIdsRef = useRef(activeProfileIds);

    useEffect(() => {
        activeProfileIdsRef.current = activeProfileIds;
    }, [activeProfileIds]);

    useEffect(() => {
        if (!isLoggedIn) {
            setSearchStatuses({});
            setActiveProfileIds([]);
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

                const runningIds = Object.entries(res)
                    .filter(([, status]) => status && ['generating', 'searching', 'analyzing'].includes(status.state))
                    .map(([id]) => String(id));
                
                // Merge server-confirmed running IDs with any IDs pending first server acknowledgement
                // (the brief window between addProfileId() being called and the first poll returning it).
                setActiveProfileIds(prev => {
                    const next = [...runningIds];
                    for (const id of activeProfileIdsRef.current) {
                        if (!res[id] && !next.includes(id)) {
                            next.push(id);
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
        setActiveProfileIds(prev => {
            const pidStr = String(pid);
            if (prev.includes(pidStr)) return prev;
            return [...prev, pidStr];
        });
    }, []);

    const removeProfileId = useCallback((pid) => {
        setActiveProfileIds(prev => prev.filter(id => id !== String(pid)));
    }, []);

    return (
        <SearchContext.Provider value={{
            searchStatuses,
            activeProfileIds,
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
