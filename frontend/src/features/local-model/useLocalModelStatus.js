import { useCallback, useEffect, useRef, useState } from "react";
import { LocalModelService } from "../../services/localModel";

const INITIAL_STATUS = {
    loading: true,
    available: false,
    ready: false,
    configured_model: "",
    installed_models: [],
    error_code: null,
};

export function useLocalModelStatus({ refreshMs = 30_000, enabled = true } = {}) {
    const [status, setStatus] = useState(INITIAL_STATUS);
    const inFlightRef = useRef(null);
    const requestControllerRef = useRef(null);

    const refresh = useCallback((callerSignal) => {
        if (!enabled) return Promise.resolve(null);
        if (inFlightRef.current) return inFlightRef.current;

        const controller = new AbortController();
        requestControllerRef.current = controller;
        const abortFromCaller = () => controller.abort();
        callerSignal?.addEventListener("abort", abortFromCaller, { once: true });
        if (callerSignal?.aborted) controller.abort();

        const request = LocalModelService.status({ signal: controller.signal, quiet: true })
            .then((result) => {
                if (!controller.signal.aborted) setStatus({ ...result, loading: false });
                return result;
            })
            .catch((error) => {
                if (!controller.signal.aborted) {
                    setStatus((current) => ({
                        ...current,
                        loading: false,
                        available: false,
                        ready: false,
                        error_code: "local_service_unreachable",
                    }));
                }
                return error;
            })
            .finally(() => {
                callerSignal?.removeEventListener("abort", abortFromCaller);
                if (requestControllerRef.current === controller) requestControllerRef.current = null;
                if (inFlightRef.current === request) inFlightRef.current = null;
            });
        inFlightRef.current = request;
        return request;
    }, [enabled]);

    useEffect(() => {
        if (!enabled) return undefined;
        const controller = new AbortController();
        const initial = window.setTimeout(() => refresh(controller.signal), 0);
        const interval = window.setInterval(() => refresh(controller.signal), refreshMs);
        const onOnline = () => refresh(controller.signal);
        window.addEventListener("online", onOnline);
        return () => {
            controller.abort();
            requestControllerRef.current?.abort();
            window.clearTimeout(initial);
            window.clearInterval(interval);
            window.removeEventListener("online", onOnline);
        };
    }, [enabled, refresh, refreshMs]);

    return { status, refresh: () => refresh() };
}
