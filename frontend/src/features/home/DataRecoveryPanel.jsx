import { useRef, useState } from "react";

import {
    isDesktopShell,
    openBackupWithNativeDialog,
    saveBackupWithNativeDialog,
    verifyArchivePayload,
} from "../../platform/desktop";
import { PortabilityService } from "../../services/portability";
import { useI18n } from "../../i18n/useI18n";
import { translateMessage } from "../../i18n/runtime";
import { BackupInspectionSummary } from "./BackupInspectionSummary";

function browserDownload({ blob, filename }) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
}

export function DataRecoveryPanel({ hasProfile }) {
    const { t } = useI18n();
    const erasePhraseRequired = t("data.erasePhrase");
    const fileInput = useRef(null);
    const selectingBackup = useRef(false);
    const [busy, setBusy] = useState("");
    const [message, setMessage] = useState(null);
    const [erasePhrase, setErasePhrase] = useState("");
    const [verifiedBackup, setVerifiedBackup] = useState(null);

    const backup = async () => {
        setBusy("backup");
        setMessage(null);
        try {
            const archive = await PortabilityService.exportArchive();
            if (isDesktopShell()) {
                const saved = await saveBackupWithNativeDialog(archive, { title: t("desktop.saveBackup") });
                setMessage({ messageKey: saved ? "data.backupSaved" : "data.saveCancelled" });
            } else {
                await verifyArchivePayload(archive);
                browserDownload(archive);
                setMessage({ messageKey: "data.backupDownloaded" });
            }
        } catch (error) {
            setMessage(error.message ? { message: error.message } : { messageKey: "data.backupFailed" });
        } finally {
            setBusy("");
        }
    };

    const inspect = async (file) => {
        if (!file) return;
        setBusy("inspect");
        setMessage(null);
        setVerifiedBackup(null);
        try {
            const inspection = await PortabilityService.inspectArchive(file);
            setVerifiedBackup({ file, inspection });
            setMessage({ messageKey: "data.inspectDone" });
        } catch (error) {
            setMessage(error.message ? { message: error.message } : { messageKey: "data.inspectFailed" });
        } finally {
            setBusy("");
            if (fileInput.current) fileInput.current.value = "";
        }
    };

    const chooseBackup = async () => {
        if (isDesktopShell()) {
            if (selectingBackup.current) return;
            selectingBackup.current = true;
            setBusy("inspect");
            setMessage(null);
            try {
                await inspect(await openBackupWithNativeDialog({ title: t("desktop.openBackup") }));
            } catch (error) {
                setMessage(error.message ? { message: error.message } : { messageKey: "data.inspectFailed" });
            } finally {
                selectingBackup.current = false;
                setBusy("");
            }
        } else {
            fileInput.current?.click();
        }
    };

    const restore = async () => {
        if (hasProfile || !verifiedBackup?.inspection.restorable) return;
        setBusy("restore");
        setMessage(null);
        let completed = false;
        try {
            await PortabilityService.restoreArchive(verifiedBackup.file);
            completed = true;
        } catch (error) {
            setMessage(error.message ? { message: error.message } : { messageKey: "data.restoreFailed" });
        } finally {
            if (!completed) setBusy("");
        }
    };

    const erase = async () => {
        setBusy("erase");
        setMessage(null);
        let completed = false;
        try {
            await PortabilityService.eraseLocalData();
            completed = true;
        } catch (error) {
            setMessage(error.message ? { message: error.message } : { messageKey: "data.eraseFailed" });
        } finally {
            if (!completed) setBusy("");
        }
    };

    return (
        <section className="surface-section home-data">
            <div className="section-heading"><div><span className="section-kicker">{t("data.privacy")}</span><h2>{t("data.title")}</h2></div><i className="bi bi-shield-lock" /></div>
            <p>{t("data.copy")}</p>
            <div className="data-actions">
                <button className="button button--secondary" type="button" onClick={backup} disabled={!hasProfile || Boolean(busy)}><i className="bi bi-download" />{busy === "backup" ? t("data.backupBusy") : t("data.backup")}</button>
                <button className="button button--secondary" type="button" onClick={chooseBackup} disabled={Boolean(busy)}><i className="bi bi-shield-check" />{busy === "inspect" ? t("data.inspectBusy") : t("data.inspect")}</button>
                <button className="button button--secondary" type="button" onClick={restore} disabled={hasProfile || !verifiedBackup?.inspection.restorable || Boolean(busy)}><i className="bi bi-upload" />{busy === "restore" ? t("data.restoreBusy") : t("data.restoreVerified")}</button>
                <input ref={fileInput} className="visually-hidden" type="file" tabIndex={-1} accept=".zip,application/zip" aria-label={t("data.backupFile")} onChange={(event) => inspect(event.target.files?.[0])} />
            </div>
            <small>{t("data.restoreRequiresEmpty")}</small>
            {verifiedBackup && <BackupInspectionSummary inspection={verifiedBackup.inspection} />}
            <div className="danger-zone">
                <label htmlFor="erase-career-data">{t("data.eraseInstruction")} <strong>{erasePhraseRequired}</strong></label>
                <div><input id="erase-career-data" className="form-control" value={erasePhrase} onChange={(event) => setErasePhrase(event.target.value)} autoComplete="off" /><button className="button button--danger" type="button" onClick={erase} disabled={erasePhrase !== erasePhraseRequired || Boolean(busy)}>{busy === "erase" ? t("data.eraseBusy") : t("data.erase")}</button></div>
            </div>
            {message && <div className="data-message" role="status">{translateMessage(message, t)}</div>}
        </section>
    );
}
