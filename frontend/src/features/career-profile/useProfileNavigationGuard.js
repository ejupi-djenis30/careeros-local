import { useEffect, useRef } from "react";
import { useBlocker } from "react-router";
import { CAREEROS_BEFORE_LOGOUT_EVENT } from "../../lib/events";

export function useProfileNavigationGuard(dirty, message) {
    const handledLocation = useRef(null);
    const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && (
        currentLocation.pathname !== nextLocation.pathname
        || currentLocation.search !== nextLocation.search
    ));

    useEffect(() => {
        if (blocker.state !== "blocked") {
            handledLocation.current = null;
            return;
        }
        if (handledLocation.current === blocker.location) return;
        handledLocation.current = blocker.location;
        if (window.confirm(message)) blocker.proceed();
        else blocker.reset();
    }, [blocker, message]);

    useEffect(() => {
        if (!dirty) return undefined;
        const preventUnload = (event) => {
            event.preventDefault();
            event.returnValue = "";
        };
        const checkLogout = (event) => {
            // Expired/revoked sessions must still lock immediately.
            if (!event.detail?.force && !window.confirm(message)) event.preventDefault();
        };
        window.addEventListener("beforeunload", preventUnload);
        window.addEventListener(CAREEROS_BEFORE_LOGOUT_EVENT, checkLogout);
        return () => {
            window.removeEventListener("beforeunload", preventUnload);
            window.removeEventListener(CAREEROS_BEFORE_LOGOUT_EVENT, checkLogout);
        };
    }, [dirty, message]);
}
