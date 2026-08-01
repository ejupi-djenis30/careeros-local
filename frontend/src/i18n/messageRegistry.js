export const SUPPORTED_LANGUAGES = Object.freeze(["en", "it"]);

const loaders = Object.freeze({
    en: () => import("./locales/en.js"),
    it: () => import("./locales/it.js"),
});
const catalogues = new Map();
const pendingLoads = new Map();

export function defineMessages(namespaces) {
    const messages = {};
    for (const [namespace, entries] of Object.entries(namespaces)) {
        if (!namespace || !entries || typeof entries !== "object" || Array.isArray(entries)) {
            throw new TypeError("Invalid message namespace");
        }
        for (const [key, value] of Object.entries(entries)) {
            messages[`${namespace}.${key}`] = value;
        }
    }
    return Object.freeze(messages);
}

function isSupported(language) {
    return SUPPORTED_LANGUAGES.includes(language);
}

export function registerMessages(language, messages) {
    if (!isSupported(language)) {
        throw new Error(`Unsupported interface language: ${language}`);
    }
    if (!messages || typeof messages !== "object") {
        throw new TypeError(`Invalid message catalogue for ${language}`);
    }
    catalogues.set(language, messages);
    return messages;
}

export function hasMessages(language) {
    return catalogues.has(language);
}

export function getMessages(language) {
    return catalogues.get(language) ?? null;
}

export function loadMessages(language) {
    if (!isSupported(language)) {
        return Promise.reject(new Error(`Unsupported interface language: ${language}`));
    }
    const loaded = getMessages(language);
    if (loaded) return Promise.resolve(loaded);

    const pending = pendingLoads.get(language);
    if (pending) return pending;

    const operation = loaders[language]()
        .then((module) => registerMessages(language, module.default))
        .finally(() => {
            if (pendingLoads.get(language) === operation) pendingLoads.delete(language);
        });
    pendingLoads.set(language, operation);
    return operation;
}
