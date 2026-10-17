import { useLayoutEffect, useRef } from "react";
import { registerModal } from "./modalStack";

export function useModalIsolation({
    isOpen,
    dialogRef,
    initialFocusRef,
    initialFocusSelector,
    onRequestClose,
    closeBlocked = false,
    returnFocus,
    backgroundRef,
    backgroundSelector,
}) {
    const closeRef = useRef(onRequestClose);
    const blockedRef = useRef(closeBlocked);
    useLayoutEffect(() => {
        closeRef.current = onRequestClose;
        blockedRef.current = closeBlocked;
    }, [closeBlocked, onRequestClose]);

    useLayoutEffect(() => {
        const dialog = dialogRef.current;
        if (!isOpen || !dialog) return undefined;
        return registerModal({
            dialog,
            initialFocus: () => initialFocusRef?.current
                || (initialFocusSelector ? dialog.querySelector(initialFocusSelector) : null),
            onRequestClose: () => closeRef.current?.(),
            closeBlocked: () => blockedRef.current,
            returnFocus,
            background: backgroundRef?.current
                || (backgroundSelector ? document.querySelector(backgroundSelector) : undefined),
        });
    }, [backgroundRef, backgroundSelector, dialogRef, initialFocusRef, initialFocusSelector, isOpen, returnFocus]);
}
