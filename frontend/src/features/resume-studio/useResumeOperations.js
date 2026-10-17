import { useCallback, useEffect, useRef } from "react";

// A selected editor session owns its requests, including their status and errors.
// Aborting a mutation cannot undo its server transaction, so completions must
// also prove that their owner is still current before changing local state.
export function useResumeOperations({ setBusy, setError, errorMessage }) {
    const active = useRef({ mounted: true, session: 0, request: null, pending: null });

    const invalidate = useCallback(() => {
        active.current.session += 1;
        active.current.request?.abort();
        active.current.request = null;
        active.current.pending = null;
        setBusy("");
        setError(null);
    }, [setBusy, setError]);

    useEffect(() => {
        const state = active.current;
        state.mounted = true;
        return () => {
            state.mounted = false;
            state.session += 1;
            state.request?.abort();
            state.pending = null;
        };
    }, []);

    const run = useCallback(async (name, operation, onError) => {
        if (!active.current.mounted || active.current.pending) return;
        active.current.request?.abort();
        const controller = new AbortController();
        const session = active.current.session;
        active.current.request = controller;
        active.current.pending = controller;
        const isCurrent = () => active.current.mounted
            && active.current.session === session
            && active.current.request === controller;
        const request = {
            isCurrent,
            isSessionCurrent: () => active.current.mounted && active.current.session === session,
            signal: controller.signal,
            options: { signal: controller.signal, suppressGlobalError: true },
        };
        setBusy(name);
        setError(null);
        try {
            return await operation(request);
        } catch (error) {
            if (isCurrent()) {
                if (onError) onError(error);
                else setError(errorMessage(error));
            }
        } finally {
            if (active.current.pending === controller) active.current.pending = null;
            if (isCurrent()) {
                setBusy("");
            }
        }
    }, [setBusy, setError, errorMessage]);

    return { invalidate, run };
}
