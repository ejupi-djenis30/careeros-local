import { ProviderAdvanced } from "./ProviderAdvanced";
import { ProviderFields } from "./ProviderFields";
import { switchAdapter } from "./providerModel";

export function ProviderEditor({ provider, setProvider, advanced, setAdvanced, onSave, onCancel, saving, message, t }) {
    return (
        <section className="surface-section provider-editor" aria-labelledby="provider-editor-title">
            <div className="section-heading"><div><span className="section-kicker">{t("providers.editorKicker")}</span><h2 id="provider-editor-title">{t(provider.id ? "providers.editTitle" : "providers.createTitle")}</h2></div><span className="section-number">02</span></div>
            <p className="section-intro">{t("providers.editorCopy")}</p>
            <form onSubmit={onSave}>
                <div className="form-grid form-grid--2">
                    <label className="field-stack"><span>{t("providers.name")}</span><input className="form-control" value={provider.display_name} onChange={(event) => setProvider({ ...provider, display_name: event.target.value })} maxLength="160" required /></label>
                    <label className="field-stack"><span>{t("providers.key")}</span><input className="form-control" value={provider.key} onChange={(event) => setProvider({ ...provider, key: event.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, "") })} pattern="[a-z][a-z0-9_-]+" maxLength="64" required /></label>
                    <label className="field-stack provider-editor__wide"><span>{t("providers.description")}</span><textarea className="form-control" value={provider.description} onChange={(event) => setProvider({ ...provider, description: event.target.value })} maxLength="2000" /></label>
                    <label className="field-stack"><span>{t("providers.adapter")}</span><select className="form-select" value={provider.adapter_kind} onChange={(event) => setProvider(switchAdapter(provider, event.target.value))}><option value="json">{t("providers.adapterJson")}</option><option value="html">{t("providers.adapterHtml")}</option></select></label>
                    <label className="check-line provider-enable"><input type="checkbox" checked={provider.enabled} onChange={(event) => setProvider({ ...provider, enabled: event.target.checked })} /><span><strong>{t("providers.enable")}</strong><small>{t("providers.enableCopy")}</small></span></label>
                    <label className="field-stack"><span>{t("providers.baseUrl")}</span><input className="form-control" type="url" value={provider.request.base_url} onChange={(event) => setProvider({ ...provider, request: { ...provider.request, base_url: event.target.value } })} placeholder={t("providers.baseUrlPlaceholder")} required /></label>
                    <label className="field-stack"><span>{t("providers.path")}</span><input className="form-control" value={provider.request.path_template} onChange={(event) => setProvider({ ...provider, request: { ...provider.request, path_template: event.target.value } })} placeholder={t("providers.pathPlaceholder")} required /></label>
                    {provider.adapter_kind === "json" ? <><label className="field-stack"><span>{t("providers.itemsPath")}</span><input className="form-control" value={provider.extraction.items_path || ""} onChange={(event) => setProvider({ ...provider, extraction: { ...provider.extraction, items_path: event.target.value } })} required /></label><label className="field-stack"><span>{t("providers.totalPath")}</span><input className="form-control" value={provider.extraction.total_path || ""} onChange={(event) => setProvider({ ...provider, extraction: { ...provider.extraction, total_path: event.target.value || null } })} /></label></> : <label className="field-stack provider-editor__wide"><span>{t("providers.itemSelector")}</span><input className="form-control" value={provider.extraction.item_selector || ""} onChange={(event) => setProvider({ ...provider, extraction: { ...provider.extraction, item_selector: event.target.value } })} placeholder={t("providers.itemSelectorPlaceholder")} required /></label>}
                </div>
                <ProviderFields provider={provider} setProvider={setProvider} t={t} />
                <ProviderAdvanced provider={provider} setProvider={setProvider} advanced={advanced} setAdvanced={setAdvanced} t={t} />
                {message && <p className="provider-editor__message" role="alert">{message}</p>}
                <div className="provider-editor__actions"><button className="button button--primary" type="submit" disabled={saving}>{saving ? t("providers.saving") : t("providers.save")}</button><button className="button button--secondary" type="button" onClick={onCancel} disabled={saving}>{t("providers.cancel")}</button></div>
            </form>
        </section>
    );
}
