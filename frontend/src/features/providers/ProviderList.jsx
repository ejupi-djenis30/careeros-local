export function ProviderList({ catalog, selectedId, onNew, onEdit, onTest, onToggle, onDelete, busy, t }) {
    const installed = catalog?.installed || [];
    return (
        <aside className="provider-list" aria-labelledby="provider-list-title">
            <div className="provider-list__heading">
                <div><span className="section-kicker">{t("providers.catalogKicker")}</span><h2 id="provider-list-title">{t("providers.catalogTitle")}</h2></div>
                <button type="button" className="button button--primary" onClick={onNew}><i className="bi bi-plus-lg" aria-hidden="true" />{t("providers.new")}</button>
            </div>
            <h3>{t("providers.installed")}</h3>
            {installed.length === 0 ? <p className="provider-list__empty">{t("providers.empty")}</p> : (
                <div className="provider-card-grid">
                    {installed.map((provider) => (
                        <article className={`provider-card ${selectedId === provider.id ? "is-selected" : ""}`} key={provider.id}>
                            <div><strong>{provider.display_name}</strong><span className={`status-pill ${provider.enabled ? "is-success" : ""}`}>{t(provider.enabled ? "providers.enabled" : "providers.disabled")}</span></div>
                            <p>{provider.description || t("providers.noDescription")}</p>
                            <code>{t("providers.providerMeta", { key: provider.key, adapter: provider.adapter_kind.toUpperCase(), revision: provider.revision })}</code>
                            {provider.source_pack_id && <small>{t("providers.fromPack", { pack: provider.source_pack_id, version: provider.source_pack_version })}</small>}
                            <div className="provider-card__actions">
                                {provider.adapter_kind !== "native" && <button type="button" className="button button--secondary" onClick={() => onEdit(provider)} disabled={busy}>{t("providers.edit")}</button>}
                                <button type="button" className="button button--secondary" onClick={() => onToggle(provider)} disabled={busy}>{t(provider.enabled ? "providers.disable" : "providers.enable")}</button>
                                <button type="button" className="button button--ghost" onClick={() => onTest(provider)} disabled={busy}>{t("providers.test")}</button>
                                <button type="button" className="button button--danger" onClick={() => onDelete(provider)} disabled={busy}>{t("providers.delete")}</button>
                            </div>
                        </article>
                    ))}
                </div>
            )}
        </aside>
    );
}
