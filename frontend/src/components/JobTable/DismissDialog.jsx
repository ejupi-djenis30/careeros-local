import React, { useEffect } from "react";
import { createPortal } from "react-dom";
import { useI18n } from "../../i18n/useI18n";

const DISMISS_OPTIONS = [
    { value: "not_interested", labelKey: "jobs.dismiss.notInterested", icon: "bi-hand-thumbs-down" },
    { value: "wrong_domain", labelKey: "jobs.dismiss.wrongDomain", icon: "bi-signpost-split" },
    { value: "too_senior", labelKey: "jobs.dismiss.tooSenior", icon: "bi-arrow-up-circle" },
    { value: "too_junior", labelKey: "jobs.dismiss.tooJunior", icon: "bi-arrow-down-circle" },
    { value: "bad_salary", labelKey: "jobs.dismiss.badSalary", icon: "bi-currency-exchange" },
    { value: "bad_location", labelKey: "jobs.dismiss.badLocation", icon: "bi-geo" },
    { value: "already_applied", labelKey: "jobs.dismiss.alreadyApplied", icon: "bi-check2-square" },
];

export function DismissDialog({ open, jobTitle, onDismiss, onClose }) {
    const { t } = useI18n();
    useEffect(() => {
        if (!open) return;
        const handleEscape = (e) => {
            if (e.key === "Escape") onClose();
        };
        document.addEventListener("keydown", handleEscape);
        return () => document.removeEventListener("keydown", handleEscape);
    }, [open, onClose]);

    if (!open) return null;

    return createPortal(
        <div
            className="position-fixed top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center animate-fade-in custom-modal-backdrop"
            onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
        >
            <div
                className="glass-panel border border-white-10 rounded-3 shadow-lg p-4 animate-slide-up"
                style={{ maxWidth: 400, width: "90%" }}
                onClick={(e) => e.stopPropagation()}
            >
                <div className="d-flex justify-content-between align-items-start mb-3">
                    <div className="min-w-0 flex-grow-1 pe-2">
                        <h6 className="text-white fw-bold mb-1">{t("jobs.dismiss.title")}</h6>
                        {jobTitle && <div className="text-secondary x-small text-truncate w-100">{jobTitle}</div>}
                    </div>
                    <button
                        onClick={onClose}
                        className="btn btn-sm btn-icon btn-secondary rounded-circle flex-shrink-0"
                        aria-label={t("common.close")}
                    >
                        <i className="bi bi-x-lg"></i>
                    </button>
                </div>

                <div className="text-secondary small mb-3">{t("jobs.dismiss.prompt")}</div>

                <div className="d-flex flex-column gap-1">
                    {DISMISS_OPTIONS.map(opt => (
                        <button
                            key={opt.value}
                            className="btn btn-sm w-100 text-start text-white-50 hover-bg-white-10 px-3 py-2 border-0 rounded-2 d-flex align-items-center gap-2"
                            onClick={() => onDismiss(opt.value)}
                        >
                            <i className={`bi ${opt.icon} opacity-50`}></i>
                            {t(opt.labelKey)}
                        </button>
                    ))}
                </div>

                <div className="mt-3 pt-3 border-top border-white-10">
                    <button
                        className="btn btn-sm btn-secondary w-100 rounded-pill"
                        onClick={onClose}
                    >
                        {t("common.cancel")}
                    </button>
                </div>
            </div>
        </div>,
        document.body
    );
}
