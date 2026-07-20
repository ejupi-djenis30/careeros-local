import React, { useEffect, useId, useRef } from "react";
import { useI18n } from "../i18n/useI18n";

const FOCUSABLE = [
  "button:not([disabled])",
  "[href]",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

export function ConfirmationDialog({
  isOpen,
  title,
  message,
  onConfirm,
  onCancel,
  confirmText,
  cancelText
}) {
  const { t } = useI18n();
  const resolvedConfirmText = confirmText ?? t("common.confirm");
  const resolvedCancelText = cancelText ?? t("common.cancel");
  const titleId = useId();
  const bodyId = useId();
  const dialogRef = useRef(null);
  const cancelRef = useRef(null);
  const cancelHandlerRef = useRef(onCancel);

  useEffect(() => {
    cancelHandlerRef.current = onCancel;
  }, [onCancel]);

  useEffect(() => {
    if (!isOpen) return;
    const previouslyFocused = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    cancelRef.current?.focus();

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        cancelHandlerRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = [...(dialogRef.current?.querySelectorAll(FOCUSABLE) || [])];
      if (focusable.length === 0) {
        event.preventDefault();
        dialogRef.current?.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
      if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus();
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div
      className="modal d-block confirm-dialog-backdrop"
      ref={dialogRef}
      tabIndex="-1"
      role="dialog"
      aria-labelledby={titleId}
      aria-describedby={bodyId}
      aria-modal="true"
      onClick={onCancel}
    >
      <div
        className="modal-dialog modal-dialog-centered"
        role="document"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-content glass-panel border-white-10">
          <div className="modal-header border-bottom border-white-10">
            <h5 className="modal-title text-light" id={titleId}>{title}</h5>
            <button
              type="button"
              className="btn-close btn-close-white"
              aria-label={t("common.close")}
              onClick={onCancel}
            ></button>
          </div>
          <div className="modal-body text-light-50" id={bodyId}>
            <p className="mb-0">{message}</p>
          </div>
          <div className="modal-footer border-top border-white-10">
            <button
              ref={cancelRef}
              type="button"
              className="btn btn-secondary glass-btn"
              onClick={onCancel}
            >
              {resolvedCancelText}
            </button>
            <button
              type="button"
              className="btn btn-danger"
              onClick={onConfirm}
            >
              {resolvedConfirmText}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
