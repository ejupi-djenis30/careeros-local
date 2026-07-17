import { useCallback, useEffect, useState } from "react";
import { LocalModelService } from "../../services/localModel";

const INITIAL_STATUS = {
    loading: true,
    available: false,
    ready: false,
    configured_model: "",
    installed_models: [],
    error_code: null,
};

export function useLocalModelStatus({ refreshMs = 30_000 } = {}) {
    const [status, setStatus] = useState(INITIAL_STATUS);

    const refresh = useCallback(async (signal) => {
        try {
            const result = await LocalModelService.status({ signal, quiet: true });
            setStatus({ ...result, loading: false });
        } catch {
            if (signal?.aborted) return;
            setStatus((current) => ({ ...current, loading: false, available: false, ready: false, error_code: "local_service_unreachable" }));
        }
    }, []);

    useEffect(() => {
        const controller = new AbortController();
        const initial = window.setTimeout(() => refresh(controller.signal), 0);
        const interval = window.setInterval(() => refresh(controller.signal), refreshMs);
        const onOnline = () => refresh(controller.signal);
        window.addEventListener("online", onOnline);
        return () => {
            controller.abort();
            window.clearTimeout(initial);
            window.clearInterval(interval);
            window.removeEventListener("online", onOnline);
        };
    }, [refresh, refreshMs]);

    return { status, refresh: () => refresh() };
}
