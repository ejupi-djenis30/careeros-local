import { useCallback, useEffect, useState } from "react";

import { bootstrapDesktop } from "../platform/desktop";

export function DesktopBoot({ children }) {
    const [attempt, setAttempt] = useState(0);
    const [status, setStatus] = useState({ state: "starting", error: null });

    useEffect(() => {
        let active = true;
        bootstrapDesktop()
            .then(() => active && setStatus({ state: "ready", error: null }))
            .catch((error) => active && setStatus({
                state: "failed",
                error: error instanceof Error ? error.message : String(error),
            }));
        return () => {
            active = false;
        };
    }, [attempt]);

    const retry = useCallback(() => {
        setStatus({ state: "starting", error: null });
        setAttempt((value) => value + 1);
    }, []);
    if (status.state === "ready") return children;
    return (
        <main className="desktop-boot" aria-live="polite">
            <img src="/careeros.svg" alt="" className="desktop-boot__mark" />
            <h1>CareerOS Local</h1>
            {status.state === "starting" ? (
                <>
                    <span className="desktop-boot__spinner" aria-hidden="true" />
                    <p>Preparazione del tuo spazio carriera privato…</p>
                </>
            ) : (
                <div className="desktop-boot__error" role="alert">
                    <h2>Il servizio locale non si è avviato</h2>
                    <p>{status.error}</p>
                    <button type="button" className="button button--primary" onClick={retry}>Riprova</button>
                </div>
            )}
        </main>
    );
}
