import React, { useState } from "react";
import { ScheduleCard } from "./ScheduleCard";
import { ConfirmationDialog } from "./ConfirmationDialog";
import { useI18n } from "../i18n/useI18n";
import { translateMessage } from "../i18n/runtime";
import { useSchedulesController } from "./useSchedulesController";
import { SCHEDULE_MESSAGES } from "./scheduleMessages";

export function Schedules() {
    const { t, language } = useI18n();
    const copy = SCHEDULE_MESSAGES[language] || SCHEDULE_MESSAGES.en;
    const [profileToDelete, setProfileToDelete] = useState(null);
    const schedules = useSchedulesController();
    const { profiles, loading, refreshing, error, refreshFailed, pendingIds, refreshProfiles } = schedules;

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
                <p className="text-secondary opacity-75 mb-3">{translateMessage(error, t)}</p>
                <button onClick={refreshProfiles} className="btn btn-outline-primary">
                    <i className="bi bi-arrow-clockwise me-2"></i>{t("schedules.retry")}
                </button>
            </div>
        );
    }

    const activeSchedules = profiles.filter((profile) => profile.schedule_enabled);

    return (
        <div className="animate-fade-in h-100 d-flex flex-column" aria-busy={refreshing}>
            {refreshFailed && (
                <div className="glass-panel p-3 mb-3" role="alert">
                    <p>{copy.refreshFailed}</p>
                    <button type="button" className="btn btn-outline-primary" onClick={refreshProfiles}>
                        {t("schedules.retry")}
                    </button>
                </div>
            )}
            {activeSchedules.length === 0 ? (
                <div className="glass-panel text-center py-5 animate-fade-in align-items-center d-flex flex-column justify-content-center h-100">
                    <div className="mb-4">
                        <div className="rounded-circle bg-success-10 d-inline-flex align-items-center justify-content-center border border-success-20 shadow-glow sz-80">
                            <i className="bi bi-clock-history fs-1 text-success"></i>
                        </div>
                    </div>
                    <h4 className="text-white fw-bold">{t("schedules.emptyTitle")}</h4>
                    <p className="text-secondary opacity-75 max-w-480">{t("schedules.emptyCopy")}</p>
                </div>
            ) : (
                <>
                    <div className="d-flex justify-content-end align-items-center mb-4">
                        <button
                            onClick={refreshProfiles}
                            disabled={refreshing}
                            className="btn btn-icon btn-secondary rounded-circle shadow-sm"
                            title={t("schedules.refresh")}
                            aria-label={t("schedules.refresh")}
                        >
                            <i className="bi bi-arrow-clockwise"></i>
                        </button>
                    </div>
                    <div className="row g-4 overflow-auto pb-4 custom-scrollbar">
                        {activeSchedules.map((profile) => (
                            <ScheduleCard
                                key={profile.id}
                                profile={profile}
                                pending={pendingIds.has(profile.id)}
                                onToggle={schedules.toggle}
                                onChangeInterval={schedules.changeInterval}
                                onDelete={setProfileToDelete}
                            />
                        ))}
                    </div>
                </>
            )}
            <ConfirmationDialog
                isOpen={profileToDelete !== null}
                title={t("schedules.removeTitle")}
                message={t("schedules.removeCopy")}
                confirmText={t("schedules.remove")}
                onConfirm={() => {
                    const id = profileToDelete;
                    setProfileToDelete(null);
                    if (id !== null) void schedules.remove(id);
                }}
                onCancel={() => setProfileToDelete(null)}
            />
        </div>
    );
}
