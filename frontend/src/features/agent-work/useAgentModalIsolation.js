import { useEffect, useRef } from "react";

const FOCUSABLE_SELECTORS = [
    "button:not([disabled])",
    "[href]",
    "input:not([disabled])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "[tabindex]:not([tabindex='-1'])",
].join(",");

export function useAgentModalIsolation({
    isOpen,
    dialogRef,
    initialFocusRef,
    onRequestClose,
    closeBlocked = false,
}) {
    const closeRef = useRef(onRequestClose);
    const blockedRef = useRef(closeBlocked);
    useEffect(() => {
        closeRef.current = onRequestClose;
        blockedRef.current = closeBlocked;
    }, [closeBlocked, onRequestClose]);

    useEffect(() => {
        if (!isOpen) return undefined;

        const previouslyFocused = document.activeElement;
        const previousOverflow = document.body.style.overflow;
        const portalRoot = dialogRef.current?.parentElement;
        const siblings = Array.from(document.body.children)
            .filter((element) => element !== portalRoot)
            .map((element) => ({ element, inert: element.inert }));

        document.body.style.overflow = "hidden";
        siblings.forEach(({ element }) => {
            element.inert = true;
        });
        (initialFocusRef.current || dialogRef.current)?.focus();

        const handleKeyDown = (event) => {
            if (event.key === "Escape") {
                if (!blockedRef.current) {
                    event.preventDefault();
                    closeRef.current?.();
                }
                return;
            }
            if (event.key !== "Tab") return;

            const focusable = Array.from(
                dialogRef.current?.querySelectorAll(FOCUSABLE_SELECTORS) || [],
            );
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
            siblings.forEach(({ element, inert }) => {
                element.inert = inert;
            });
            if (previouslyFocused instanceof HTMLElement && document.contains(previouslyFocused)) {
                previouslyFocused.focus();
            }
        };
    }, [dialogRef, initialFocusRef, isOpen]);
}
