import { createContext } from "react";
import { getMessages, hasMessages } from "./messageRegistry";

function interpolate(template, variables) {
    return template.replace(/\{(\w+)\}/g, (_match, key) => String(variables[key] ?? `{${key}}`));
}

export function createTranslator(language) {
    const catalogue = getMessages(language);
    if (!catalogue) {
        throw new Error(`Message catalogue is not loaded: ${language}`);
    }
    const englishFallback = language === "en" ? catalogue : getMessages("en");
    return (key, variables = {}) => interpolate(
        catalogue[key] ?? englishFallback?.[key] ?? key,
        variables,
    );
}

export function translateMessage(message, t) {
    if (!message) return "";
    if (typeof message === "string") return message;
    const variables = Object.fromEntries(
        Object.entries(message.variables || {}).map(([key, value]) => [
            key,
            value && typeof value === "object" && (value.messageKey || value.message)
                ? translateMessage(value, t)
                : value,
        ]),
    );
    return message.messageKey ? t(message.messageKey, variables) : message.message || "";
}

export const I18nContext = createContext({
    language: "en",
    setLanguage: () => {},
    pendingLanguage: null,
    languageError: false,
    t: hasMessages("en") ? createTranslator("en") : (key) => key,
});
