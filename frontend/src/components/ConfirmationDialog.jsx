import React, { useEffect, useId } from "react";

export function ConfirmationDialog({
  isOpen,
  title,
  message,
  onConfirm,
  onCancel,
  confirmText = "Confirm",
  cancelText = "Cancel"
}) {
  const titleId = useId();
  const bodyId = useId();

  useEffect(() => {
    if (!isOpen) return;
    document.body.style.overflow = "hidden";
    const handleEscape = (e) => { if (e.key === "Escape") onCancel(); };
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", handleEscape);
    };
  }, [isOpen, onCancel]);

  if (!isOpen) return null;

  return (
    <div
      className="modal d-block confirm-dialog-backdrop"
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
              aria-label="Close"
              onClick={onCancel}
            ></button>
          </div>
          <div className="modal-body text-light-50" id={bodyId}>
            <p className="mb-0">{message}</p>
          </div>
          <div className="modal-footer border-top border-white-10">
            <button
              type="button"
              className="btn btn-secondary glass-btn"
              onClick={onCancel}
            >
              {cancelText}
            </button>
            <button
              type="button"
              className="btn btn-danger"
              onClick={onConfirm}
            >
              {confirmText}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
