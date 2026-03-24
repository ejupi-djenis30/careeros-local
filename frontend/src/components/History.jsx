import React, { useState, useEffect } from "react";
import { SearchService } from "../services/search";
import { HistoryCard } from "./HistoryCard";

export function History({ onStartSearch, onUseAsTemplate, onSaveAsSchedule }) {
    const [profiles, setProfiles] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadProfiles();
    }, []);

    const loadProfiles = async () => {
        try {
            const data = await SearchService.getProfiles();
            // Sort by ID descending (newest first)
            setProfiles(data.sort((a, b) => b.id - a.id));
        } catch (e) {
            console.error("Failed to load profiles:", e);
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="d-flex justify-content-center align-items-center h-100">
                <div className="spinner-border text-primary" role="status"></div>
            </div>
        );
    }

    if (!profiles.length) {
        return (
            <div className="glass-panel text-center py-5 animate-fade-in align-items-center d-flex flex-column justify-content-center h-100">
                <div className="mb-4">
                    <div className="rounded-circle bg-secondary bg-opacity-10 d-inline-flex align-items-center justify-content-center" style={{ width: 80, height: 80 }}>
                        <i className="bi bi-journal-x fs-1 text-secondary opacity-50"></i>
                    </div>
                </div>
                <h4 className="text-white fw-bold">No History</h4>
                <p className="text-secondary opacity-75">Your past searches will appear here.</p>
            </div>
        );
    }

    return (
        <div className="animate-fade-in h-100 d-flex flex-column">
            <div className="d-flex justify-content-end align-items-center mb-4">
                <button 
                    onClick={loadProfiles} 
                    className="btn btn-icon btn-secondary rounded-circle shadow-sm"
                    title="Refresh List"
                >
                    <i className="bi bi-arrow-clockwise"></i>
                </button>
            </div>

            <div className="d-flex flex-column gap-3 overflow-auto custom-scrollbar pb-3">
                {profiles.map(p => (
                    <HistoryCard
                        key={p.id}
                        profile={p}
                        onStartSearch={onStartSearch}
                        onUseAsTemplate={onUseAsTemplate}
                        onSaveAsSchedule={onSaveAsSchedule}
                    />
                ))}
            </div>
        </div>
    );
}
