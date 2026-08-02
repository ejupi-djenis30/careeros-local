import { useEffect, useState } from "react";
import { useI18n } from "../../i18n/useI18n";
import { ProviderService } from "../../services/providers";
import { ProviderEditor } from "./ProviderEditor";
import { ProviderImporter } from "./ProviderImporter";
import { ProviderList } from "./ProviderList";
import { advancedText, emptyProvider, payloadForSave, providerForEdit } from "./providerModel";
import "./providers.css";

export function ProvidersPage() {
    const { t } = useI18n();
    const [catalog, setCatalog] = useState({ installed: [], available_packs: [] });
    const [provider, setProvider] = useState(emptyProvider);
    const [advanced, setAdvanced] = useState(() => advancedText(emptyProvider()));
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState("");
    const [testResult, setTestResult] = useState(null);

    const load = async (signal) => {
        const data = await ProviderService.list(signal);
        setCatalog(data);
        return data;
    };
    useEffect(() => {
        let active = true;
        const controller = new AbortController();
        ProviderService.list(controller.signal)
            .then((data) => {
                if (active) setCatalog(data);
            })
            .catch(() => {
                if (active) setMessage(t("providers.loadError"));
            })
            .finally(() => {
                if (active) setLoading(false);
            });
        return () => {
            active = false;
            controller.abort();
        };
    }, [t]);

    const edit = (value) => { const next = providerForEdit(value); setProvider(next); setAdvanced(advancedText(next)); setMessage(""); setTestResult(null); };
    const reset = () => edit(emptyProvider());
    const save = async (event) => {
        event.preventDefault(); setBusy(true); setMessage(""); setTestResult(null);
        try {
            const payload = payloadForSave(provider, { ...advanced, invalidJson: t("providers.invalidJson") });
            const { expected_revision: _revision, ...validationPayload } = payload;
            await ProviderService.validate(validationPayload);
            const saved = provider.id ? await ProviderService.update(provider.id, payload) : await ProviderService.create(payload);
            await load(); edit(saved); setMessage(t("providers.saved"));
        } catch (error) { setMessage(error?.message || t("providers.saveError")); }
        finally { setBusy(false); }
    };
    const test = async (value) => {
        setBusy(true); setMessage(""); setTestResult(null);
        try {
            const result = await ProviderService.test(value.id, { query: "software engineer", location: "", language: "en" });
            if (value.adapter_kind !== "native") edit(value);
            setTestResult(result);
        }
        catch (error) { setMessage(error?.message || t("providers.testError")); }
        finally { setBusy(false); }
    };
    const remove = async (value) => {
        if (!window.confirm(t("providers.deleteConfirm", { name: value.display_name }))) return;
        setBusy(true); setMessage("");
        try { await ProviderService.remove(value.id, value.revision); await load(); if (provider.id === value.id) reset(); }
        catch (error) { setMessage(error?.message || t("providers.deleteError")); }
        finally { setBusy(false); }
    };
    const importDocument = async (document, activate, localError) => {
        if (localError || !document) {
            setMessage(localError?.message || t("providers.importInvalid"));
            return;
        }
        setBusy(true); setMessage(""); setTestResult(null);
        try {
            const result = await ProviderService.importDocument(document, activate);
            await load();
            setMessage(t("providers.imported", { count: result.imported.length }));
        } catch (error) { setMessage(error?.message || t("providers.importError")); }
        finally { setBusy(false); }
    };
    const importPack = async (packId, activate) => {
        setBusy(true); setMessage(""); setTestResult(null);
        try {
            const result = await ProviderService.importPack(packId, activate);
            await load();
            setMessage(t("providers.imported", { count: result.imported.length }));
        } catch (error) { setMessage(error?.message || t("providers.importError")); }
        finally { setBusy(false); }
    };
    const toggle = async (value) => {
        setBusy(true); setMessage(""); setTestResult(null);
        try {
            const saved = await ProviderService.setState(value.id, value.revision, !value.enabled);
            await load();
            if (provider.id === value.id && saved.adapter_kind !== "native") edit(saved);
            setMessage(t(saved.enabled ? "providers.enabledMessage" : "providers.disabledMessage"));
        } catch (error) { setMessage(error?.message || t("providers.stateError")); }
        finally { setBusy(false); }
    };
    if (loading) return <div className="state-panel" role="status">{t("providers.loading")}</div>;
    return (
        <div className="providers-workspace">
            <section className="providers-hero"><div><span className="section-kicker">{t("providers.kicker")}</span><h1>{t("providers.title")}</h1><p>{t("providers.copy")}</p></div><div className="providers-hero__guard"><i className="bi bi-shield-check" aria-hidden="true" /><span>{t("providers.guard")}</span></div></section>
            <ProviderImporter packs={catalog.available_packs || []} onImportDocument={importDocument} onImportPack={importPack} busy={busy} t={t} />
            {message && <div className="provider-workspace__message" role="status">{message}</div>}
            <ProviderList catalog={catalog} selectedId={provider.id} onNew={reset} onEdit={edit} onTest={test} onToggle={toggle} onDelete={remove} busy={busy} t={t} />
            <ProviderEditor provider={provider} setProvider={setProvider} advanced={advanced} setAdvanced={setAdvanced} onSave={save} onCancel={reset} saving={busy} message="" t={t} />
            {testResult && <section className="surface-section provider-test-result" aria-live="polite"><h2>{t("providers.testResult", { count: testResult.returned_count })}</h2>{testResult.sample.length ? <ul>{testResult.sample.map((item) => <li key={item.id}><strong>{item.title}</strong><span>{[item.company, item.location].filter(Boolean).join(" · ")}</span></li>)}</ul> : <p>{t("providers.testEmpty")}</p>}</section>}
        </div>
    );
}
