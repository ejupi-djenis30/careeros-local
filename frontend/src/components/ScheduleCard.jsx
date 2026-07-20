import React, { useState } from 'react';
import { useI18n } from '../i18n/useI18n';

const SCHEDULE_PRESETS = [1, 3, 6, 12, 24];

export function ScheduleCard({ profile, onToggle, onChangeInterval, onDelete }) {
    const { t } = useI18n();
    const [isTogglePending, setIsTogglePending] = useState(false);

    const handleToggle = async () => {
        if (isTogglePending) return;
        setIsTogglePending(true);
        try {
            await onToggle(profile.id, profile.schedule_enabled, profile.schedule_interval_hours);
        } finally {
            setIsTogglePending(false);
        }
    };

    return (
        <div className="col-12 col-md-6 col-xl-4">
            <div className="glass-panel p-4 h-100 d-flex flex-column hover-y-2 transition-transform shadow-sm">
                <div className="d-flex justify-content-between align-items-start mb-3">
                    <div className="d-flex align-items-center gap-3">
                        <div className="rounded-circle bg-success bg-gradient d-flex align-items-center justify-content-center text-white shadow-glow border border-white-10" style={{ width: 48, height: 48 }}>
                            <i className="bi bi-robot fs-4"></i>
                        </div>
                        <div>
                            <h6 className="text-white mb-0 fw-bold">{profile.name || t("schedule.campaign", { id: profile.id })}</h6>
                            <div className="d-flex align-items-center gap-2 mt-1">
                                <span className="badge bg-success-10 text-success border border-success-20 rounded-pill px-2 py-1" style={{ fontSize: '0.65rem' }}>{t("schedule.active")}</span>
                                <span className="text-secondary x-small font-monospace">{t("schedule.identifier", { id: profile.id })}</span>
                            </div>
                        </div>
                    </div>
                </div>

                <hr className="border-white-10 my-3 opacity-50" />

                <div className="flex-grow-1 mb-4">
                    <div className="d-flex flex-column gap-2">
                        <div className="d-flex align-items-start text-white-50 small">
                            <i className="bi bi-briefcase me-2 mt-1 text-primary"></i>
                            <span className="text-white fw-medium text-truncate-2" title={profile.role_description}>{profile.role_description}</span>
                        </div>
                        <div className="d-flex align-items-center text-white-50 small">
                            <i className="bi bi-geo-alt me-2 text-primary"></i>
                            <span>{profile.location_filter || t("schedule.anyLocation")}</span>
                        </div>
                    </div>
                </div>

                <div className="bg-black-20 rounded-3 p-3 border border-white-5">
                    <div className="d-flex align-items-center justify-content-between mb-3">
                        <div className="d-flex align-items-center gap-2">
                            <i className="bi bi-arrow-repeat text-white"></i>
                            <span className="text-white small fw-bold">{t("schedule.interval")}</span>
                        </div>
                        <div className="form-check form-switch m-0">
                            <input
                                className="form-check-input"
                                type="checkbox"
                                checked={profile.schedule_enabled || false}
                                onChange={handleToggle}
                                disabled={isTogglePending}
                                style={{ cursor: isTogglePending ? 'wait' : 'pointer', transform: 'scale(1.1)' }}
                                title={isTogglePending ? t("schedule.updating") : t("schedule.toggle")}
                                aria-label={isTogglePending ? t("schedule.updating") : t("schedule.toggle")}
                            />
                        </div>
                    </div>

                    <div className="d-flex flex-column gap-2">
                        <div className="d-flex gap-2">
                            <input
                                type="number"
                                min="1"
                                step="1"
                                className="form-control form-control-sm bg-black-20 border-white-10 text-white shadow-none"
                                value={profile.schedule_interval_hours || 24}
                                onChange={(e) => onChangeInterval(profile.id, e.target.value)}
                            />

                            <button
                                className="btn btn-sm btn-outline-danger border-white-10 text-danger hover-bg-danger hover-text-white rounded-3 px-3 transition-colors"
                                onClick={() => onDelete(profile.id)}
                                title={t("schedule.delete")}
                                aria-label={t("schedule.delete")}
                            >
                                <i className="bi bi-trash"></i>
                            </button>
                        </div>
                        <div className="d-flex flex-wrap gap-1">
                            {SCHEDULE_PRESETS.map((hours) => (
                                <button
                                    key={hours}
                                    type="button"
                                    className={`btn btn-sm px-2 py-0 rounded-pill ${profile.schedule_interval_hours == hours ? 'btn-light text-dark fw-bold' : 'btn-outline-secondary opacity-75'}`}
                                    onClick={() => onChangeInterval(profile.id, String(hours))}
                                >
                                    {hours}h
                                </button>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
