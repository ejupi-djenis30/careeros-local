import React, { useState, useEffect } from "react";
import { SearchService } from "../services/search";
import { useToast } from "../context/ToastContext";
import { ScheduleCard } from "./ScheduleCard";
import { ConfirmationDialog } from "./ConfirmationDialog";

export function Schedules() {
    const { showToast } = useToast();
    const [profiles, setProfiles] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [profileToDelete, setProfileToDelete] = useState(null);

    useEffect(() => {
        loadProfiles();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const loadProfiles = async () => {
        setError(null);
        setLoading(true);
        try {
            const data = await SearchService.getProfiles();
            setProfiles(data);
        } catch (e) {
            console.error("Failed to load profiles:", e);
            setError("Failed to load schedules.");
            showToast("Failed to load schedules. Please refresh.");
        } finally {
            setLoading(false);
        }
    };

    const handleToggle = async (profileId, currentEnabled, intervalHours) => {
        try {
            await SearchService.toggleSchedule(profileId, !currentEnabled, intervalHours);
            loadProfiles();
        } catch (e) {
            showToast("Failed to toggle schedule: " + e.message);
        }
    };

    const handleDeleteRequest = (profileId) => {
        setProfileToDelete(profileId);
    };

    const handleConfirmDelete = async () => {
        if (!profileToDelete) return;
        try {
            await SearchService.toggleSchedule(profileToDelete, false);
            loadProfiles();
        } catch (e) {
            showToast("Failed to remove schedule: " + e.message);
        } finally {
            setProfileToDelete(null);
        }
    };

    const handleCancelDelete = () => {
        setProfileToDelete(null);
    };

    const handleChangeInterval = async (profileId, newInterval) => {
        try {
            await SearchService.toggleSchedule(profileId, true, parseInt(newInterval));
            loadProfiles();
        } catch (e) {
            showToast("Failed to update interval: " + e.message);
        }
    };

    if (loading) {
        return (
            <div className="d-flex justify-content-center align-items-center h-100">
                <div className="spinner-border text-primary" role="status"></div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="glass-panel text-center py-5 animate-fade-in align-items-center d-flex flex-column justify-content-center h-100">
                <i className="bi bi-exclamation-triangle-fill fs-1 text-danger mb-3"></i>
                <p className="text-secondary opacity-75 mb-3">{error}</p>
                <button onClick={loadProfiles} className="btn btn-outline-primary">
                    <i className="bi bi-arrow-clockwise me-2"></i>Try again
                </button>
            </div>
        );
    }

    const activeSchedules = profiles.filter(p => p.schedule_enabled);

    if (activeSchedules.length === 0) {
        return (
            <div className="glass-panel text-center py-5 animate-fade-in align-items-center d-flex flex-column justify-content-center h-100">
                <div className="mb-4">
                    <div className="rounded-circle bg-success-10 d-inline-flex align-items-center justify-content-center border border-success-20 shadow-glow sz-80">
                        <i className="bi bi-clock-history fs-1 text-success"></i>
                    </div>
                </div>
                <h4 className="text-white fw-bold">No Active Schedules</h4>
                <p className="text-secondary opacity-75 max-w-480">Enable "Automatic Search" when creating a new search to let the agent work for you.</p>
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
                        onDelete={handleDeleteRequest}
                    />
                ))}
            </div>

            <ConfirmationDialog
                isOpen={!!profileToDelete}
                title="Remove Schedule"
                message="Remove this schedule? The history will be preserved."
                confirmText="Remove"
                onConfirm={handleConfirmDelete}
                onCancel={handleCancelDelete}
            />
        </div>
    );
}
