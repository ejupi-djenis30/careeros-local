import { useRef, useState } from "react";

const MAX_IMPORT_BYTES = 256 * 1024;

export function ProviderImporter({ packs, onImportDocument, onImportPack, busy, t }) {
    const inputRef = useRef(null);
    const [activate, setActivate] = useState(false);

    const importFile = async (event) => {
        const file = event.target.files?.[0];
        if (!file) return;
        try {
            if (file.size > MAX_IMPORT_BYTES) throw new Error(t("providers.importTooLarge"));
            let document;
            try {
                document = JSON.parse(await file.text());
            } catch {
                throw new Error(t("providers.importInvalid"));
            }
            await onImportDocument(document, activate);
        } catch (error) {
            await onImportDocument(null, activate, error);
        } finally {
            if (inputRef.current) inputRef.current.value = "";
        }
    };

    return (
        <section className="surface-section provider-importer" aria-labelledby="provider-import-title">
            <div className="section-heading">
                <div>
                    <span className="section-kicker">{t("providers.importKicker")}</span>
                    <h2 id="provider-import-title">{t("providers.importTitle")}</h2>
                </div>
                <span className="section-number">01</span>
            </div>
            <p className="section-intro">{t("providers.importCopy")}</p>
            <label className="check-line provider-importer__consent">
                <input
                    type="checkbox"
                    checked={activate}
                    onChange={(event) => setActivate(event.target.checked)}
                />
                <span>
                    <strong>{t("providers.activateOnImport")}</strong>
                    <small>{t("providers.activateOnImportCopy")}</small>
                </span>
            </label>
            <div className="provider-pack-grid">
                {packs.length === 0 ? (
                    <p className="provider-list__empty">{t("providers.noPacks")}</p>
                ) : packs.map((pack) => (
                    <article className="provider-pack-card" key={pack.id}>
                        <div>
                            <strong>{pack.name}</strong>
                            <span className="status-pill">v{pack.version}</span>
                        </div>
                        <p>{pack.description}</p>
                        <small>{t("providers.packContents", { providers: pack.provider_keys.join(", ") })}</small>
                        <button
                            type="button"
                            className="button button--secondary"
                            onClick={() => onImportPack(pack.id, activate)}
                            disabled={busy}
                        >
                            {t("providers.importPack")}
                        </button>
                    </article>
                ))}
            </div>
            <div className="provider-importer__file">
                <label className="field-stack" htmlFor="provider-document-file">
                    <span>{t("providers.importFile")}</span>
                    <input
                        ref={inputRef}
                        id="provider-document-file"
                        className="form-control"
                        type="file"
                        accept="application/json,.json"
                        onChange={importFile}
                        disabled={busy}
                    />
                    <small>{t("providers.importFileCopy")}</small>
                </label>
            </div>
        </section>
    );
}
