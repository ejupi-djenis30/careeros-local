import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LocalModelService } from "../../services/localModel";
import { ConfirmationDialog } from "../../components/ConfirmationDialog";
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

export function ModelManager({ status: controlledStatus = null, onRefresh = null }) {
    const { t } = useI18n();
    const localSource = useLocalModelStatus({ refreshMs: 2_000, enabled: controlledStatus === null });
    const status = controlledStatus || localSource.status;
    const refresh = onRefresh || localSource.refresh;
    const [catalog, setCatalog] = useState(null);
    const [catalogState, setCatalogState] = useState("loading");
    const catalogController = useRef(null);
    const [selectionOverride, setSelectionOverride] = useState("");
    const [accepted, setAccepted] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [catalogError, setCatalogError] = useState("");
    const [confirmRemoval, setConfirmRemoval] = useState(false);

    const loadCatalog = useCallback(async () => {
        catalogController.current?.abort();
        const controller = new AbortController();
        catalogController.current = controller;
        setCatalogState("loading");
        setCatalogError("");
        try {
            const result = await LocalModelService.catalog({ signal: controller.signal });
            if (controller.signal.aborted) return;
            setCatalog(result);
            setCatalogState("ready");
        } catch (reason) {
            if (controller.signal.aborted) return;
            setCatalogState("failed");
            setCatalogError(reason.message || t("model.catalogUnavailable"));
        } finally {
            if (catalogController.current === controller) catalogController.current = null;
        }
    }, [t]);

    useEffect(() => {
        const initialLoad = window.setTimeout(() => void loadCatalog(), 0);
        return () => {
            window.clearTimeout(initialLoad);
            catalogController.current?.abort();
        };
    }, [loadCatalog]);

    const managed = status.managed || {};
    const selected = selectionOverride || managed.model_key || catalog?.models?.[0]?.key || "";
    const model = useMemo(() => catalog?.models?.find((item) => item.key === selected), [catalog, selected]);
    const active = ACTIVE_PHASES.has(managed.phase);
    const paused = managed.phase === "paused";
    const canRemove = managed.model_installed || managed.runtime_installed || paused;
    const progress = managed.bytes_total > 0
        ? Math.min(100, Math.round((managed.bytes_downloaded / managed.bytes_total) * 100))
        : 0;

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
        <div className="model-manager" aria-busy={busy || active}>
            <LocalModelStatus status={status} onRefresh={refresh} />

            {catalogState === "loading" && (
                <p className="model-manager__operation" role="status">{t("model.loadingCatalog")}</p>
            )}

            {catalogState === "failed" && (
                <div className="model-manager__catalog-error" role="alert">
                    <p>{catalogError || t("model.catalogUnavailable")}</p>
                    <button type="button" className="button button--secondary" onClick={loadCatalog}>
                        {t("model.retryCatalog")}
                    </button>
                </div>
            )}

            {!active && catalog?.models?.length > 1 && (
                <label>
                    {t("model.local")}
                    <select value={selected} onChange={(event) => { setSelectionOverride(event.target.value); setAccepted(false); }}>
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
                    {canRemove && <button type="button" className="button button--ghost" disabled={busy} onClick={() => setConfirmRemoval(true)}>{t("model.removeInstallation")}</button>}
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
                    <button type="button" className="button button--ghost" disabled={busy} onClick={() => setConfirmRemoval(true)}>{t("model.remove")}</button>
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

            {busy && <p className="model-manager__operation" role="status">{t("model.operationInProgress")}</p>}
            {error && <p className="field-error" role="alert">{error}</p>}

            <ConfirmationDialog
                isOpen={confirmRemoval}
                title={t("model.removeConfirmTitle")}
                message={t("model.removeConfirmCopy")}
                confirmText={t("model.removeConfirmAction")}
                onCancel={() => setConfirmRemoval(false)}
                onConfirm={() => {
                    setConfirmRemoval(false);
                    void perform(() => LocalModelService.remove());
                }}
            />
        </div>
    );
}
