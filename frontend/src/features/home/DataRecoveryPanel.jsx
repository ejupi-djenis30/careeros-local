import { useRef, useState } from "react";

import {
    isDesktopShell,
    openBackupWithNativeDialog,
    saveBackupWithNativeDialog,
} from "../../platform/desktop";
import { PortabilityService } from "../../services/portability";
import { useI18n } from "../../i18n/useI18n";
import { translateMessage } from "../../i18n/runtime";

function browserDownload({ blob, filename }) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
}

export function DataRecoveryPanel({ hasProfile, onErased }) {
    const { t } = useI18n();
    const erasePhraseRequired = t("data.erasePhrase");
    const fileInput = useRef(null);
    const [busy, setBusy] = useState("");
    const [message, setMessage] = useState(null);
    const [erasePhrase, setErasePhrase] = useState("");

    const backup = async () => {
        setBusy("backup");
        setMessage(null);
        try {
            const archive = await PortabilityService.exportArchive();
            const saved = await saveBackupWithNativeDialog(archive, { title: t("desktop.saveBackup") });
            if (!isDesktopShell()) browserDownload(archive);
            setMessage({ messageKey: saved || !isDesktopShell() ? "data.backupSaved" : "data.saveCancelled" });
        } catch (error) {
            setMessage(error.message ? { message: error.message } : { messageKey: "data.backupFailed" });
        } finally {
            setBusy("");
        }
    };

    const restore = async (file) => {
        if (!file) return;
        setBusy("restore");
        setMessage(null);
        try {
            const result = await PortabilityService.restoreArchive(file);
            setMessage({
                messageKey: "data.restoreDone",
                variables: {
                    files: result.restored_files,
                    records: Object.values(result.restored_records).reduce((sum, count) => sum + count, 0),
                },
            });
            window.location.reload();
        } catch (error) {
            setMessage(error.message ? { message: error.message } : { messageKey: "data.restoreFailed" });
        } finally {
            setBusy("");
            if (fileInput.current) fileInput.current.value = "";
        }
    };

    const chooseRestore = async () => {
        if (isDesktopShell()) {
            await restore(await openBackupWithNativeDialog({ title: t("desktop.openBackup") }));
        } else {
            fileInput.current?.click();
        }
    };

    const erase = async () => {
        setBusy("erase");
        setMessage(null);
        try {
            const result = await PortabilityService.eraseLocalData();
            setErasePhrase("");
            setMessage({ messageKey: "data.eraseDone", variables: { files: result.files + result.model_files } });
            onErased?.();
        } catch (error) {
            setMessage(error.message ? { message: error.message } : { messageKey: "data.eraseFailed" });
        } finally {
            setBusy("");
        }
    };

    return (
        <section className="surface-section home-data">
            <div className="section-heading"><div><span className="section-kicker">{t("data.privacy")}</span><h2>{t("data.title")}</h2></div><i className="bi bi-shield-lock" /></div>
            <p>{t("data.copy")}</p>
            <div className="data-actions">
                <button className="button button--secondary" type="button" onClick={backup} disabled={!hasProfile || Boolean(busy)}><i className="bi bi-download" />{busy === "backup" ? t("data.backupBusy") : t("data.backup")}</button>
                <button className="button button--secondary" type="button" onClick={chooseRestore} disabled={hasProfile || Boolean(busy)}><i className="bi bi-upload" />{busy === "restore" ? t("data.restoreBusy") : t("data.restore")}</button>
                <input ref={fileInput} className="visually-hidden" type="file" accept=".zip,application/zip" aria-label={t("data.backupFile")} onChange={(event) => restore(event.target.files?.[0])} />
            </div>
            {hasProfile && <small>{t("data.restoreRequiresEmpty")}</small>}
            <div className="danger-zone">
                <label htmlFor="erase-career-data">{t("data.eraseInstruction")} <strong>{erasePhraseRequired}</strong></label>
                <div><input id="erase-career-data" className="form-control" value={erasePhrase} onChange={(event) => setErasePhrase(event.target.value)} autoComplete="off" /><button className="button button--danger" type="button" onClick={erase} disabled={erasePhrase !== erasePhraseRequired || Boolean(busy)}>{busy === "erase" ? t("data.eraseBusy") : t("data.erase")}</button></div>
            </div>
            {message && <div className="data-message" role="status">{translateMessage(message, t)}</div>}
        </section>
    );
}
