import { useEffect, useMemo, useState } from "react";
import { LocalModelService } from "../../services/localModel";
import { LocalModelStatus } from "./LocalModelStatus";
import { useLocalModelStatus } from "./useLocalModelStatus";
import { useI18n } from "../../i18n/useI18n";

const ACTIVE_PHASES = new Set(["downloading_runtime", "installing_runtime", "downloading_model", "starting"]);
const DOWNLOAD_PHASES = new Set(["downloading_runtime", "downloading_model"]);

function formatBytes(value) {
    if (!Number.isFinite(value) || value <= 0) return "0 MB";
    const gigabytes = value / (1024 ** 3);
    return gigabytes >= 1 ? `${gigabytes.toFixed(1)} GB` : `${Math.round(value / (1024 ** 2))} MB`;
}

export function ModelManager() {
    const { t } = useI18n();
    const { status, refresh } = useLocalModelStatus({ refreshMs: 2_000 });
    const [catalog, setCatalog] = useState(null);
    const [selected, setSelected] = useState("");
    const [accepted, setAccepted] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
        const controller = new AbortController();
        LocalModelService.catalog({ signal: controller.signal })
            .then((result) => {
                setCatalog(result);
                setSelected((current) => current || result.models?.[0]?.key || "");
            })
            .catch((reason) => {
                if (!controller.signal.aborted) setError(reason.message || t("model.catalogUnavailable"));
            });
        return () => controller.abort();
    }, [t]);

    const model = useMemo(() => catalog?.models?.find((item) => item.key === selected), [catalog, selected]);
    const managed = status.managed || {};
    const active = ACTIVE_PHASES.has(managed.phase);
    const paused = managed.phase === "paused";
    const canRemove = managed.model_installed || managed.runtime_installed || paused;
    const progress = managed.bytes_total > 0
        ? Math.min(100, Math.round((managed.bytes_downloaded / managed.bytes_total) * 100))
        : 0;

    useEffect(() => {
        if (managed.model_key) setSelected((current) => current || managed.model_key);
    }, [managed.model_key]);

    async function perform(action) {
        setBusy(true);
        setError("");
        try {
            await action();
            await refresh();
        } catch (reason) {
            setError(reason.message || t("model.operationFailed"));
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="model-manager">
            <LocalModelStatus />

            {!active && catalog?.models?.length > 1 && (
                <label>
                    {t("model.local")}
                    <select value={selected} onChange={(event) => { setSelected(event.target.value); setAccepted(false); }}>
                        {catalog.models.map((item) => (
                            <option key={item.key} value={item.key}>{item.displayName}</option>
                        ))}
                    </select>
                </label>
            )}

            {!status.ready && !active && !paused && model && (
                <div className="model-manager__setup">
                    <div className="model-manager__model">
                        <div>
                            <strong>{model.displayName}</strong>
                            <span>{model.parameters} · {model.quantization} · {formatBytes(model.sizeBytes)}</span>
                        </div>
                        <span className="model-manager__license">{model.license}</span>
                    </div>
                    <p>{t("model.verifiedDownload")}</p>
                    <label className="model-manager__consent">
                        <input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} />
                        {t("model.acceptLicense", { license: model.license, size: formatBytes(model.sizeBytes) })}
                    </label>
                    <button
                        type="button"
                        className="button button--primary"
                        disabled={!accepted || busy}
                        onClick={() => perform(() => (
                            managed.model_installed && managed.model_key !== selected
                                ? LocalModelService.replace(selected)
                                : LocalModelService.install(selected)
                        ))}
                    >
                        {managed.model_installed && managed.model_key !== selected
                            ? t("model.replace")
                            : managed.error_code ? t("model.retryInstall") : t("model.install")}
                    </button>
                    {canRemove && <button type="button" className="button button--ghost" disabled={busy} onClick={() => perform(() => LocalModelService.remove())}>{t("model.removeInstallation")}</button>}
                </div>
            )}

            {active && (
                <div className="model-manager__progress" aria-live="polite">
                    <div><strong>{managed.phase === "starting" ? t("model.starting") : t("model.installing")}</strong><span>{progress}% · {formatBytes(managed.bytes_downloaded)} / {formatBytes(managed.bytes_total)}</span></div>
                    <progress max="100" value={progress}>{progress}%</progress>
                    {DOWNLOAD_PHASES.has(managed.phase) && <button type="button" className="button button--ghost" disabled={busy} onClick={() => perform(() => LocalModelService.pause())}>{t("model.pause")}</button>}
                    {managed.phase !== "starting" && <button type="button" className="button button--ghost" disabled={busy} onClick={() => perform(() => LocalModelService.cancel())}>{t("model.cancel")}</button>}
                </div>
            )}

            {paused && (
                <div className="model-manager__progress" aria-live="polite">
                    <div><strong>{t("model.paused")}</strong><span>{progress}% · {formatBytes(managed.bytes_downloaded)} / {formatBytes(managed.bytes_total)}</span></div>
                    <progress max="100" value={progress}>{progress}%</progress>
                    <button type="button" className="button button--primary" disabled={busy} onClick={() => perform(() => LocalModelService.resume())}>{t("model.resume")}</button>
                    <button type="button" className="button button--ghost" disabled={busy} onClick={() => perform(() => LocalModelService.cancel())}>{t("model.cancel")}</button>
                </div>
            )}

            {status.ready && (
                <div className="model-manager__ready">
                    <span>{t("model.loopback")}</span>
                    <button type="button" className="button button--ghost" disabled={busy} onClick={() => perform(() => LocalModelService.restart())}>{t("model.restart")}</button>
                    <button type="button" className="button button--ghost" disabled={busy} onClick={() => perform(() => LocalModelService.remove())}>{t("model.remove")}</button>
                </div>
            )}

            {status.ready && managed.model_key !== selected && model && (
                <div className="model-manager__setup">
                    <p>{t("model.replaceCopy")}</p>
                    <label className="model-manager__consent">
                        <input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)} />
                        {t("model.acceptReplacement", { license: model.license, model: model.displayName })}
                    </label>
                    <button type="button" className="button button--primary" disabled={!accepted || busy} onClick={() => perform(() => LocalModelService.replace(selected))}>{t("model.replace")}</button>
                </div>
            )}

            {error && <p className="field-error" role="alert">{error}</p>}
        </div>
    );
}
