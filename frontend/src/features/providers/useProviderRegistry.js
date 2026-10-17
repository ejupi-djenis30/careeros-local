import { useCallback, useEffect, useRef, useState } from "react";
import { ProviderService } from "../../services/providers";
import { advancedText, emptyProvider, payloadForSave, providerForEdit } from "./providerModel";

export function useProviderRegistry(t) {
    const [catalog, setCatalog] = useState(null);
    const [provider, setProvider] = useState(emptyProvider);
    const [advanced, setAdvanced] = useState(() => advancedText(emptyProvider()));
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState("");
    const [testResult, setTestResult] = useState(null);
    const state = useRef({ mounted: true, controller: null, busy: false });
    const translator = useRef(t);
    useEffect(() => { translator.current = t; }, [t]);

    const load = useCallback(async (signal) => {
        const data = await ProviderService.list(signal);
        if (state.current.mounted && !signal.aborted) setCatalog(data);
    }, []);
    const reload = useCallback(async () => {
        if (state.current.busy) return;
        state.current.controller?.abort();
        const controller = new AbortController();
        state.current.controller = controller;
        setLoading(true);
        setMessage("");
        try { await load(controller.signal); }
        catch { if (!controller.signal.aborted) setMessage(translator.current("providers.loadError")); }
        finally { if (!controller.signal.aborted && state.current.mounted) setLoading(false); }
    }, [load]);
    useEffect(() => {
        const owner = state.current;
        owner.mounted = true;
        void reload();
        return () => { owner.mounted = false; owner.controller?.abort(); };
    }, [reload]);

    const select = (value) => {
        const next = providerForEdit(value);
        setProvider(next);
        setAdvanced(advancedText(next));
        setMessage("");
        setTestResult(null);
    };
    const edit = (value) => { if (!state.current.busy) select(value); };
    const reset = () => edit(emptyProvider());
    const run = async (operation, fallback) => {
        if (!state.current.mounted || state.current.busy) return;
        state.current.controller?.abort();
        const controller = new AbortController();
        state.current.controller = controller;
        state.current.busy = true;
        const current = () => state.current.mounted && !controller.signal.aborted;
        setBusy(true);
        setMessage("");
        setTestResult(null);
        try { await operation(controller.signal, current); }
        catch (error) { if (current()) setMessage(error?.message || t(fallback)); }
        finally {
            if (current()) { state.current.busy = false; setBusy(false); }
        }
    };
    const save = async (event) => {
        event.preventDefault();
        await run(async (signal, current) => {
            const payload = payloadForSave(provider, { ...advanced, invalidJson: t("providers.invalidJson") });
            const { expected_revision: _revision, ...validation } = payload;
            const checked = await ProviderService.validate(validation, signal);
            if (!current()) return;
            if (checked.valid !== true) throw new Error(t("providers.invalidConfiguration"));
            const saved = provider.id
                ? await ProviderService.update(provider.id, payload, signal)
                : await ProviderService.create(payload, signal);
            if (!current()) return;
            await load(signal);
            if (current()) { select(saved); setMessage(t("providers.saved")); }
        }, "providers.saveError");
    };
    const test = async (value) => {
        if (state.current.busy || !window.confirm(t("providers.testConsent", { name: value.display_name }))) return;
        await run(async (signal, current) => {
            const result = await ProviderService.test(value.id, { query: "software engineer", location: "", language: "en", allow_network: true }, signal);
            if (current()) setTestResult(result);
        }, "providers.testError");
    };
    const remove = async (value) => {
        if (state.current.busy || !window.confirm(t("providers.deleteConfirm", { name: value.display_name }))) return;
        await run(async (signal, current) => {
            await ProviderService.remove(value.id, value.revision, signal);
            if (!current()) return;
            await load(signal);
            if (current() && provider.id === value.id) select(emptyProvider());
        }, "providers.deleteError");
    };
    const importDocument = async (document, activate, localError) => {
        if (!state.current.mounted || state.current.busy) return;
        if (localError || !document) { setMessage(localError?.message || t("providers.importInvalid")); return; }
        await run(async (signal, current) => {
            const result = await ProviderService.importDocument(document, activate, signal);
            if (!current()) return;
            await load(signal);
            if (current()) setMessage(t("providers.imported", { count: result.imported.length }));
        }, "providers.importError");
    };
    const importPack = async (packId, activate) => run(async (signal, current) => {
        const result = await ProviderService.importPack(packId, activate, signal);
        if (!current()) return;
        await load(signal);
        if (current()) setMessage(t("providers.imported", { count: result.imported.length }));
    }, "providers.importError");
    const toggle = async (value) => run(async (signal, current) => {
        const saved = await ProviderService.setState(value.id, value.revision, !value.enabled, signal);
        if (!current()) return;
        await load(signal);
        if (!current()) return;
        if (provider.id === value.id && saved.adapter_kind !== "native") select(saved);
        setMessage(t(saved.enabled ? "providers.enabledMessage" : "providers.disabledMessage"));
    }, "providers.stateError");

    return { catalog, provider, setProvider, advanced, setAdvanced, loading, busy, message, testResult,
        reload, edit, reset, save, test, remove, importDocument, importPack, toggle };
}
