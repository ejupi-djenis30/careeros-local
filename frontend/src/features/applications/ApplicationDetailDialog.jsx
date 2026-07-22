import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { ApplicationDetail } from "./ApplicationDetail";

const FOCUSABLE = [
    "a[href]",
    "button:not([disabled])",
    "input:not([disabled])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "[tabindex]:not([tabindex='-1'])",
].join(",");

function focusableChildren(dialog) {
    return Array.from(dialog?.querySelectorAll(FOCUSABLE) ?? []).filter(
        (element) => !element.hasAttribute("hidden") && element.getAttribute("aria-hidden") !== "true",
    );
}

export function ApplicationDetailDialog({
    application,
    resumeVersions,
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

    useEffect(() => {
        const previouslyFocused = document.activeElement;
        const background = backgroundRef.current ?? document.querySelector(".workspace-layout");
        const hadInert = background?.hasAttribute("inert") ?? false;
        const previousAriaHidden = background?.getAttribute("aria-hidden") ?? null;
        const previousOverflow = document.body.style.overflow;

        background?.setAttribute("inert", "");
        background?.setAttribute("aria-hidden", "true");
        document.body.style.overflow = "hidden";
        const initialFocus = dialogRef.current?.querySelector("[data-dialog-initial-focus]");
        (initialFocus ?? dialogRef.current)?.focus({ preventScroll: true });

        const handleKeyDown = (event) => {
            if (event.key === "Escape") {
                event.preventDefault();
                closeHandlerRef.current?.();
                return;
            }
            if (event.key !== "Tab") return;
            const focusable = focusableChildren(dialogRef.current);
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (!first || !last) {
                event.preventDefault();
                dialogRef.current?.focus();
            } else if (!dialogRef.current?.contains(document.activeElement)) {
                event.preventDefault();
                (event.shiftKey ? last : first).focus();
            } else if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        };
        document.addEventListener("keydown", handleKeyDown);
        return () => {
            document.removeEventListener("keydown", handleKeyDown);
            document.body.style.overflow = previousOverflow;
            if (background) {
                if (!hadInert) background.removeAttribute("inert");
                if (previousAriaHidden === null) background.removeAttribute("aria-hidden");
                else background.setAttribute("aria-hidden", previousAriaHidden);
            }
            const focusTarget = returnFocus instanceof HTMLElement ? returnFocus : previouslyFocused;
            if (focusTarget instanceof HTMLElement && document.contains(focusTarget)) {
                focusTarget.focus({ preventScroll: true });
            }
        };
    }, [backgroundRef, returnFocus]);

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
                onChanged={onChanged}
                onClose={() => closeHandlerRef.current?.()}
                dialogRef={dialogRef}
            />
        </div>,
        document.body,
    );
}
