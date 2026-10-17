import React, { useId, useRef } from "react";
import { createPortal } from "react-dom";
import { useModalIsolation } from "./modals/useModalIsolation";
import { useI18n } from "../i18n/useI18n";

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
  useModalIsolation({
    isOpen,
    dialogRef,
    initialFocusRef: cancelRef,
    onRequestClose: onCancel,
  });

  if (!isOpen) return null;

  return createPortal(
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
    </div>,
    document.body,
  );
}
