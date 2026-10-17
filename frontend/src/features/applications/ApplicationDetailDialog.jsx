import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { ApplicationDetail } from "./ApplicationDetail";
import { useModalIsolation } from "../../components/modals/useModalIsolation";

export function ApplicationDetailDialog({
    application,
    resumeVersions,
    resumeDrafts,
    resumeMetadataStatus,
    onRetryResumeMetadata,
    onChanged,
    onClose,
    returnFocus,
    backgroundRef,
}) {
    const dialogRef = useRef(null);
    const closeHandlerRef = useRef(onClose);

    useEffect(() => {
        closeHandlerRef.current = onClose;
    }, [onClose]);

    useModalIsolation({
        isOpen: true,
        dialogRef,
        initialFocusSelector: "[data-dialog-initial-focus]",
        onRequestClose: onClose,
        returnFocus,
        backgroundRef,
        backgroundSelector: ".workspace-layout",
    });

    return createPortal(
        <div
            className="application-detail-scrim"
            onClick={(event) => {
                if (event.target === event.currentTarget) closeHandlerRef.current?.();
            }}
        >
            <ApplicationDetail
                application={application}
                resumeVersions={resumeVersions}
                resumeDrafts={resumeDrafts}
                resumeMetadataStatus={resumeMetadataStatus}
                onRetryResumeMetadata={onRetryResumeMetadata}
                onChanged={onChanged}
                onClose={() => closeHandlerRef.current?.()}
                dialogRef={dialogRef}
            />
        </div>,
        document.body,
    );
}
