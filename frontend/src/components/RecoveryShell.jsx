import { useEffect, useRef, useState } from "react";

import { CAREEROS_MARK_URL } from "../app/brand";
import { useAuth } from "../context/AuthContext";
import { LanguageSwitcher } from "../i18n/LanguageSwitcher";
import { useI18n } from "../i18n/useI18n";
import { isDesktopShell, openBackupWithNativeDialog } from "../platform/desktop";
import { CareerService } from "../services/career";
import { PortabilityService } from "../services/portability";
import { VaultMaintenance } from "../services/vaultMaintenance";

const COPY_BY_STATE = Object.freeze({
    reset_pending: {
        title: "recovery.resetTitle",
        copy: "recovery.resetCopy",
        action: "recovery.retryReset",
        busy: "recovery.retryingReset",
        failure: "recovery.resetFailed",
    },
    restore_pending: {
        title: "recovery.restoreTitle",
        copy: "recovery.restoreCopy",
        action: "recovery.retryRestore",
        busy: "recovery.retryingRestore",
        failure: "recovery.restoreFailed",
    },
    erasure_pending: {
        title: "recovery.erasureTitle",
        copy: "recovery.erasureCopy",
        action: "recovery.retryErasure",
        busy: "recovery.retryingErasure",
        failure: "recovery.erasureFailed",
    },
});

export function RecoveryShell() {
    const { logout, maintenanceSession } = useAuth();
    const { t } = useI18n();
    const fileInput = useRef(null);
    const operationRef = useRef(null);
    const titleRef = useRef(null);
    const [busy, setBusy] = useState("");
    const [errorKey, setErrorKey] = useState(null);
    const [erasePhrase, setErasePhrase] = useState("");
    const [hasRestoreArchive, setHasRestoreArchive] = useState(
        () => Boolean(VaultMaintenance.getRestoreArchive()),
    );

    const sessionState = maintenanceSession?.sessionState;
    const reauthRequired = maintenanceSession?.reauthRequired === true;
    useEffect(() => {
        if (!sessionState) return undefined;
        const frame = window.requestAnimationFrame(() => {
            titleRef.current?.focus({ preventScroll: true });
        });
        return () => window.cancelAnimationFrame(frame);
    }, [reauthRequired, sessionState]);

    if (!maintenanceSession) return null;

    const copy = COPY_BY_STATE[sessionState] || COPY_BY_STATE.erasure_pending;
    const erasePhraseRequired = t("data.erasePhrase");

    const run = async (operation, action, failureKey = copy.failure) => {
        if (operationRef.current) return;
        operationRef.current = operation;
        setBusy(operation);
        setErrorKey(null);
        let completed = false;
        try {
            const result = await action();
            completed = result !== false;
        } catch {
            setErrorKey(failureKey);
            setHasRestoreArchive(Boolean(VaultMaintenance.getRestoreArchive()));
        } finally {
            if (!completed) setBusy("");
            operationRef.current = null;
        }
    };

    const retryRestore = async (file = VaultMaintenance.getRestoreArchive()) => {
        if (!file) return;
        await run("restore", () => PortabilityService.restoreArchive(file));
    };

    const chooseRestoreArchive = async () => {
        if (isDesktopShell()) {
            return run("restore", async () => {
                const file = await openBackupWithNativeDialog({ title: t("desktop.openBackup") });
                if (!file) return false;
                return PortabilityService.restoreArchive(file);
            });
        }
        fileInput.current?.click();
    };

    const retryPendingOperation = () => {
        if (sessionState === "reset_pending") {
            return run("reset", () => CareerService.resetVault());
        }
        if (sessionState === "restore_pending") {
            if (!hasRestoreArchive) return chooseRestoreArchive();
            return retryRestore();
        }
        return run("erasure", () => PortabilityService.eraseLocalData());
    };

    const eraseEverything = () => run(
        "erasure",
        () => PortabilityService.eraseLocalData(),
        "recovery.erasureFailed",
    );

    const signInAgain = () => {
        VaultMaintenance.clearRetryState();
        void logout({ force: true });
    };

    const primaryOperation = sessionState.replace("_pending", "");
    const actionLabel = sessionState === "restore_pending" && !hasRestoreArchive
        ? t("recovery.chooseSameArchive")
        : t(busy === primaryOperation ? copy.busy : copy.action);

    return (
        <main className="recovery-shell">
            <section className="recovery-panel" aria-labelledby="recovery-title">
                <header className="recovery-panel__header">
                    <div className="workspace-brand">
                        <img className="workspace-brand__mark" src={CAREEROS_MARK_URL} alt="" width="40" height="40" />
                        <div><strong>CareerOS</strong><span>{t("recovery.localRecovery")}</span></div>
                    </div>
                    <LanguageSwitcher />
                </header>

                <div className="recovery-panel__intro">
                    <span className="recovery-panel__mark"><i className="bi bi-shield-exclamation" aria-hidden="true" /></span>
                    <div>
                        <span className="section-kicker">{t("recovery.kicker")}</span>
                        <h1 ref={titleRef} id="recovery-title" tabIndex="-1">{t(copy.title)}</h1>
                        <p>{t(copy.copy)}</p>
                    </div>
                </div>

                {reauthRequired ? (
                    <div className="inline-alert inline-alert--warning" role="status">
                        {t("recovery.reauthRequired")}
                    </div>
                ) : (
                    <button
                        type="button"
                        className="button button--primary button--wide"
                        disabled={Boolean(busy)}
                        onClick={() => { void retryPendingOperation(); }}
                    >
                        {actionLabel}
                    </button>
                )}

                {!reauthRequired && sessionState === "restore_pending" && (
                    <input
                        ref={fileInput}
                        className="visually-hidden"
                        type="file"
                        tabIndex={-1}
                        accept=".zip,application/zip"
                        aria-label={t("recovery.sameArchiveFile")}
                        onChange={(event) => {
                            const file = event.target.files?.[0];
                            event.target.value = "";
                            if (file) void retryRestore(file);
                        }}
                    />
                )}

                {!reauthRequired && sessionState !== "erasure_pending" && (
                    <section className="recovery-erasure" aria-labelledby="recovery-erasure-title">
                        <h2 id="recovery-erasure-title">{t("recovery.eraseFallbackTitle")}</h2>
                        <p>{t("recovery.eraseFallbackCopy")}</p>
                        <label htmlFor="recovery-erase-phrase">
                            {t("recovery.eraseInstruction")} <strong>{erasePhraseRequired}</strong>
                        </label>
                        <div>
                            <input
                                id="recovery-erase-phrase"
                                className="form-control"
                                value={erasePhrase}
                                onChange={(event) => setErasePhrase(event.target.value)}
                                autoComplete="off"
                            />
                            <button
                                type="button"
                                className="button button--danger"
                                disabled={erasePhrase !== erasePhraseRequired || Boolean(busy)}
                                onClick={() => { void eraseEverything(); }}
                            >
                                {busy === "erasure" ? t("recovery.retryingErasure") : t("recovery.eraseAll")}
                            </button>
                        </div>
                    </section>
                )}

                {errorKey && !reauthRequired && (
                    <div className="inline-alert inline-alert--danger" role="alert">{t(errorKey)}</div>
                )}

                <footer className="recovery-panel__footer">
                    <p>{t("recovery.noWorkspaceAccess")}</p>
                    <button
                        type="button"
                        className="button button--secondary"
                        disabled={Boolean(busy)}
                        onClick={signInAgain}
                    >
                        {t("recovery.signInAgain")}
                    </button>
                </footer>
            </section>
        </main>
    );
}
