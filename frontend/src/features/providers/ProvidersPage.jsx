import { useMemo } from "react";
import { useI18n } from "../../i18n/useI18n";
import { ProviderEditor } from "./ProviderEditor";
import { ProviderImporter } from "./ProviderImporter";
import { ProviderList } from "./ProviderList";
import { useProviderRegistry } from "./useProviderRegistry";
import { createProviderTranslator, useProviderMessages } from "./providerMessages";
import "./providers.css";

export function ProvidersPage() {
    const { language, t } = useI18n();
    const copy = useProviderMessages(language);
    if (!copy.messages) return <div className="state-panel" role="status">{t("shell.loading")}</div>;
    return <ProviderWorkspace messages={copy.messages} messagesReady={copy.ready} />;
}

function ProviderWorkspace({ messages, messagesReady }) {
    const { t: baseTranslate } = useI18n();
    const t = useMemo(() => createProviderTranslator(messages, baseTranslate), [messages, baseTranslate]);
    const registry = useProviderRegistry(t);
    const { catalog, provider, loading, busy, message, testResult } = registry;
    if (!messagesReady || loading) return <div className="state-panel" role="status">{baseTranslate("shell.loading")}</div>;
    if (!catalog) return <div className="state-panel state-panel--danger" role="alert"><p>{message}</p><button type="button" className="button button--secondary" onClick={registry.reload}>{t("providers.retry")}</button></div>;
    return (
        <div className="providers-workspace">
            <section className="providers-hero"><div><span className="section-kicker">{t("providers.kicker")}</span><h1>{t("providers.title")}</h1><p>{t("providers.copy")}</p></div><div className="providers-hero__guard"><i className="bi bi-shield-check" aria-hidden="true" /><span>{t("providers.guard")}</span></div></section>
            <ProviderImporter packs={catalog.available_packs || []} onImportDocument={registry.importDocument} onImportPack={registry.importPack} busy={busy} t={t} />
            {message && <div className="provider-workspace__message" role="status">{message}</div>}
            <ProviderList catalog={catalog} selectedId={provider.id} onNew={registry.reset} onEdit={registry.edit} onTest={registry.test} onToggle={registry.toggle} onDelete={registry.remove} busy={busy} t={t} />
            <ProviderEditor provider={provider} setProvider={registry.setProvider} advanced={registry.advanced} setAdvanced={registry.setAdvanced} onSave={registry.save} onCancel={registry.reset} saving={busy} message="" t={t} />
            {testResult && <section className="surface-section provider-test-result" aria-live="polite"><h2>{t("providers.testResult", { count: testResult.returned_count })}</h2>{testResult.sample.length ? <ul>{testResult.sample.map((item) => <li key={item.id}><strong>{item.title}</strong><span>{[item.company, item.location].filter(Boolean).join(" · ")}</span></li>)}</ul> : <p>{t("providers.testEmpty")}</p>}</section>}
        </div>
    );
}
