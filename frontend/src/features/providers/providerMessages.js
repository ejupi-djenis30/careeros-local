import { useEffect, useState } from "react";
import { interpolate } from "../../i18n/runtime";

const loaders = Object.freeze({
    en: () => import("./locales/providers-en.js"),
    it: () => import("./locales/providers-it.js"),
});
const catalogues = new Map();
const pending = new Map();

export function loadProviderMessages(language) {
    if (!Object.hasOwn(loaders, language)) return Promise.reject(new Error("Unsupported provider language"));
    if (catalogues.has(language)) return Promise.resolve(catalogues.get(language));
    if (pending.has(language)) return pending.get(language);
    const operation = loaders[language]()
        .then(({ default: messages }) => { catalogues.set(language, messages); return messages; })
        .finally(() => { pending.delete(language); });
    pending.set(language, operation);
    return operation;
}

export function createProviderTranslator(messages, fallback) {
    return (key, variables = {}) => messages[key] === undefined
        ? fallback(key, variables)
        : interpolate(messages[key], variables);
}

export function useProviderMessages(language) {
    const [loaded, setLoaded] = useState(() => ({ language, messages: catalogues.get(language) ?? null }));
    useEffect(() => {
        let active = true;
        void loadProviderMessages(language).then(
            (messages) => { if (active) setLoaded({ language, messages }); },
            (error) => { if (active) setLoaded({ language, messages: null, error }); },
        );
        return () => { active = false; };
    }, [language]);
    if (loaded.language === language && loaded.error) throw loaded.error;
    // Keep the mounted workspace and its unsaved draft while another local language loads.
    return { ...loaded, ready: loaded.language === language && Boolean(loaded.messages) };
}
