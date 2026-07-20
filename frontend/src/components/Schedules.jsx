import React, { useCallback, useEffect, useRef, useState } from "react";
import { SearchService } from "../services/search";
import { useToast } from "../context/ToastContext";
import { ScheduleCard } from "./ScheduleCard";
import { ConfirmationDialog } from "./ConfirmationDialog";
import { useI18n } from "../i18n/useI18n";

export function Schedules() {
    const { showToast } = useToast();
    const { t } = useI18n();
    const [profiles, setProfiles] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [profileToDelete, setProfileToDelete] = useState(null);
    const requestIdRef = useRef(0);
    const requestControllerRef = useRef(null);

    const loadProfiles = useCallback(() => {
        const requestId = requestIdRef.current + 1;
        requestIdRef.current = requestId;
        requestControllerRef.current?.abort();
        const controller = new AbortController();
        requestControllerRef.current = controller;

        return SearchService.getProfiles({ signal: controller.signal })
            .then((data) => {
                if (controller.signal.aborted || requestId !== requestIdRef.current) return;
                setProfiles(Array.isArray(data) ? data : []);
                setError(null);
            })
            .catch((loadError) => {
                if (controller.signal.aborted || loadError?.name === "AbortError" || requestId !== requestIdRef.current) return;
                console.error("Failed to load profiles:", loadError);
                setError(t("schedules.loadFailed"));
                showToast(t("schedules.loadFailedRefresh"));
            })
            .finally(() => {
                if (!controller.signal.aborted && requestId === requestIdRef.current) {
                    requestControllerRef.current = null;
                    setLoading(false);
                }
            });
    }, [showToast, t]);

    const refreshProfiles = useCallback(() => {
        setError(null);
        setLoading(true);
        void loadProfiles();
    }, [loadProfiles]);

    useEffect(() => {
        void loadProfiles();
        return () => {
            requestIdRef.current += 1;
            requestControllerRef.current?.abort();
            requestControllerRef.current = null;
        };
    }, [loadProfiles]);

    const handleToggle = async (profileId, currentEnabled, intervalHours) => {
        try {
            await SearchService.toggleSchedule(profileId, !currentEnabled, intervalHours);
            await loadProfiles();
        } catch (e) {
            showToast(t("schedules.toggleFailed", { error: e.message }));
        }
    };

    const handleDeleteRequest = (profileId) => {
        setProfileToDelete(profileId);
    };

    const handleConfirmDelete = async () => {
        if (!profileToDelete) return;
        try {
            await SearchService.toggleSchedule(profileToDelete, false);
            await loadProfiles();
        } catch (e) {
            showToast(t("schedules.removeFailed", { error: e.message }));
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
            await loadProfiles();
        } catch (e) {
            showToast(t("schedules.intervalFailed", { error: e.message }));
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
                <button onClick={refreshProfiles} className="btn btn-outline-primary">
                    <i className="bi bi-arrow-clockwise me-2"></i>{t("schedules.retry")}
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
                <h4 className="text-white fw-bold">{t("schedules.emptyTitle")}</h4>
                <p className="text-secondary opacity-75 max-w-480">{t("schedules.emptyCopy")}</p>
            </div>
        );
    }

    return (
        <div className="animate-fade-in h-100 d-flex flex-column">
            <div className="d-flex justify-content-end align-items-center mb-4">
                <button
                    onClick={refreshProfiles}
                    className="btn btn-icon btn-secondary rounded-circle shadow-sm"
                    title={t("schedules.refresh")}
                    aria-label={t("schedules.refresh")}
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
                title={t("schedules.removeTitle")}
                message={t("schedules.removeCopy")}
                confirmText={t("schedules.remove")}
                onConfirm={handleConfirmDelete}
                onCancel={handleCancelDelete}
            />
        </div>
    );
}
