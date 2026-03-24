/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useState, useEffect } from 'react';
import { SearchService } from '../services/search';
import { useAuth } from './AuthContext';

const SearchContext = createContext(null);

export function SearchProvider({ children }) {
    const { isLoggedIn } = useAuth();
    const [searchStatuses, setSearchStatuses] = useState({});
    const [activeProfileIds, setActiveProfileIds] = useState([]);

    useEffect(() => {
        if (!isLoggedIn) {
            // eslint-disable-next-line react-hooks/set-state-in-effect
            setSearchStatuses({});
            setActiveProfileIds([]);
            return;
        }
        let timeoutId;
        let pollingInterval = 1500;

        const pollStatuses = async () => {
            try {
                const res = await SearchService.getAllStatuses();
                setSearchStatuses(res);

                let hasRunning = false;
                const runningIds = Object.entries(res)
                    .filter(([, status]) => {
                        const isRunning = status && ['generating', 'searching', 'analyzing'].includes(status.state);
                        if (isRunning) hasRunning = true;
                        return isRunning;
                    })
                    .map(([id]) => String(id));
                
                if (runningIds.length > 0) {
                    setActiveProfileIds(prev => {
                        const next = [...prev];
                        let changed = false;
                        for (const id of runningIds) {
                            if (!next.includes(id)) {
                                next.push(id);
                                changed = true;
                            }
                        }
                        return changed ? next : prev;
                    });
                }
                
                pollingInterval = hasRunning ? 1500 : 15000;
            } catch (e) {
                console.error("Failed to poll statuses:", e);
                pollingInterval = 15000;
            } finally {
                timeoutId = setTimeout(pollStatuses, pollingInterval);
            }
        };

        pollStatuses();
        return () => clearTimeout(timeoutId);
    }, [isLoggedIn]);

    const addProfileId = (pid) => {
        setActiveProfileIds(prev => {
            const pidStr = String(pid);
            if (prev.includes(pidStr)) return prev;
            return [...prev, pidStr];
        });
    };

    const removeProfileId = (pid) => {
        setActiveProfileIds(prev => prev.filter(id => id !== String(pid)));
    };

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
