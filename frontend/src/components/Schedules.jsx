import React, { useState, useEffect } from "react";
import { SearchService } from "../services/search";
import { ScheduleCard } from "./ScheduleCard";

export function Schedules() {
    const [profiles, setProfiles] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadProfiles();
    }, []);

    const loadProfiles = async () => {
        try {
            const data = await SearchService.getProfiles();
            setProfiles(data);
        } catch (e) {
            console.error("Failed to load profiles:", e);
        } finally {
            setLoading(false);
        }
    };

    const handleToggle = async (profileId, currentEnabled, intervalHours) => {
        try {
            await SearchService.toggleSchedule(profileId, !currentEnabled, intervalHours);
            loadProfiles();
        } catch (e) {
            alert("Failed to toggle schedule: " + e.message);
        }
    };

    const handleDelete = async (profileId) => {
        if (!window.confirm("Remove this schedule? The history will be preserved.")) return;
        try {
            await SearchService.toggleSchedule(profileId, false);
            loadProfiles();
        } catch (e) {
            alert("Failed to remove schedule: " + e.message);
        }
    };

    const handleChangeInterval = async (profileId, newInterval) => {
        try {
            await SearchService.toggleSchedule(profileId, true, parseInt(newInterval));
            loadProfiles();
        } catch (e) {
            alert("Failed to update interval: " + e.message);
        }
    };

    if (loading) {
        return (
            <div className="d-flex justify-content-center align-items-center h-100">
                <div className="spinner-border text-primary" role="status"></div>
            </div>
        );
    }

    const activeSchedules = profiles.filter(p => p.schedule_enabled);

    if (activeSchedules.length === 0) {
        return (
            <div className="glass-panel text-center py-5 animate-fade-in align-items-center d-flex flex-column justify-content-center h-100">
                <div className="mb-4">
                    <div className="rounded-circle bg-success-10 d-inline-flex align-items-center justify-content-center border border-success-20 shadow-glow" style={{ width: 80, height: 80 }}>
                        <i className="bi bi-clock-history fs-1 text-success"></i>
                    </div>
                </div>
                <h4 className="text-white fw-bold">No Active Schedules</h4>
                <p className="text-secondary opacity-75 max-w-sm">Enable "Automatic Search" when creating a new search to let the agent work for you.</p>
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

            <div className="row g-4 overflow-auto pb-4 custom-scrollbar">
                {activeSchedules.map(p => (
                    <ScheduleCard
                        key={p.id}
                        profile={p}
                        onToggle={handleToggle}
                        onChangeInterval={handleChangeInterval}
                        onDelete={handleDelete}
                    />
                ))}
            </div>
        </div>
    );
}
