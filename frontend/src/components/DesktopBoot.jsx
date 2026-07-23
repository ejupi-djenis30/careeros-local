import { useCallback, useEffect, useState } from "react";

import { bootstrapDesktop, reportDesktopReady } from "../platform/desktop";
import { useI18n } from "../i18n/useI18n";
import { CAREEROS_MARK_URL } from "../app/brand";

export function DesktopBoot({ children }) {
    const { t } = useI18n();
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
    if (status.state === "ready") return <DesktopReadySignal>{children}</DesktopReadySignal>;
    return (
        <main className="desktop-boot" aria-live="polite">
            <img src={CAREEROS_MARK_URL} alt="" className="desktop-boot__mark" />
            <h1>CareerOS Local</h1>
            {status.state === "starting" ? (
                <>
                    <span className="desktop-boot__spinner" aria-hidden="true" />
                    <p>{t("desktop.starting")}</p>
                </>
            ) : (
                <div className="desktop-boot__error" role="alert">
                    <h2>{t("desktop.failed")}</h2>
                    <p>{status.error}</p>
                    <button type="button" className="button button--primary" onClick={retry}>{t("desktop.retry")}</button>
                </div>
            )}
        </main>
    );
}

function DesktopReadySignal({ children }) {
    useEffect(() => {
        reportDesktopReady().catch(() => {
            // In production this signal is best-effort. Package smoke mode will time out if the
            // Tauri bridge or committed React tree cannot complete the handshake.
        });
    }, []);
    return children;
}
