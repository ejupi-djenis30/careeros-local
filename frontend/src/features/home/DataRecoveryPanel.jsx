import { useRef, useState } from "react";

import {
    isDesktopShell,
    openBackupWithNativeDialog,
    saveBackupWithNativeDialog,
} from "../../platform/desktop";
import { PortabilityService } from "../../services/portability";

const ERASE_PHRASE = "CANCELLA I MIEI DATI";

function browserDownload({ blob, filename }) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
}

export function DataRecoveryPanel({ hasProfile, onErased }) {
    const fileInput = useRef(null);
    const [busy, setBusy] = useState("");
    const [message, setMessage] = useState("");
    const [erasePhrase, setErasePhrase] = useState("");

    const backup = async () => {
        setBusy("backup");
        setMessage("");
        try {
            const archive = await PortabilityService.exportArchive();
            const saved = await saveBackupWithNativeDialog(archive);
            if (!isDesktopShell()) browserDownload(archive);
            setMessage(saved || !isDesktopShell() ? "Backup verificato e salvato." : "Salvataggio annullato.");
        } catch (error) {
            setMessage(error.message || "Impossibile creare il backup.");
        } finally {
            setBusy("");
        }
    };

    const restore = async (file) => {
        if (!file) return;
        setBusy("restore");
        setMessage("");
        try {
            const result = await PortabilityService.restoreArchive(file);
            setMessage(`Ripristino completato: ${result.restored_files} file e ${Object.values(result.restored_records).reduce((sum, count) => sum + count, 0)} record.`);
            window.location.reload();
        } catch (error) {
            setMessage(error.message || "Impossibile ripristinare il backup.");
        } finally {
            setBusy("");
            if (fileInput.current) fileInput.current.value = "";
        }
    };

    const chooseRestore = async () => {
        if (isDesktopShell()) {
            await restore(await openBackupWithNativeDialog());
        } else {
            fileInput.current?.click();
        }
    };

    const erase = async () => {
        setBusy("erase");
        setMessage("");
        try {
            const result = await PortabilityService.eraseLocalData();
            setErasePhrase("");
            setMessage(`Dati locali cancellati. Rimossi ${result.files + result.model_files} file gestiti.`);
            onErased?.();
        } catch (error) {
            setMessage(error.message || "Impossibile cancellare i dati locali.");
        } finally {
            setBusy("");
        }
    };

    return (
        <section className="surface-section home-data">
            <div className="section-heading"><div><span className="section-kicker">Privacy</span><h2>Backup e dati locali</h2></div><i className="bi bi-shield-lock" /></div>
            <p>Il backup ZIP contiene profilo, obiettivi, CV, allegati, candidature e audit AI. Modello e runtime si reinstallano dal catalogo verificato.</p>
            <div className="data-actions">
                <button className="button button--secondary" type="button" onClick={backup} disabled={!hasProfile || Boolean(busy)}><i className="bi bi-download" />{busy === "backup" ? "Creazione…" : "Crea backup"}</button>
                <button className="button button--secondary" type="button" onClick={chooseRestore} disabled={hasProfile || Boolean(busy)}><i className="bi bi-upload" />{busy === "restore" ? "Ripristino…" : "Ripristina backup"}</button>
                <input ref={fileInput} className="visually-hidden" type="file" accept=".zip,application/zip" aria-label="File backup CareerOS Local" onChange={(event) => restore(event.target.files?.[0])} />
            </div>
            {hasProfile && <small>Per evitare fusioni ambigue, il ripristino è disponibile solo dopo aver svuotato il Career Vault.</small>}
            <div className="danger-zone">
                <label htmlFor="erase-career-data">Per cancellare vault, audit e modello locale, scrivi <strong>{ERASE_PHRASE}</strong></label>
                <div><input id="erase-career-data" className="form-control" value={erasePhrase} onChange={(event) => setErasePhrase(event.target.value)} autoComplete="off" /><button className="button button--danger" type="button" onClick={erase} disabled={erasePhrase !== ERASE_PHRASE || Boolean(busy)}>{busy === "erase" ? "Cancellazione…" : "Cancella dati"}</button></div>
            </div>
            {message && <div className="data-message" role="status">{message}</div>}
        </section>
    );
}
