import { createContext } from "react";
import { MESSAGES } from "./messages";

function interpolate(template, variables) {
    return template.replace(/\{(\w+)\}/g, (_match, key) => String(variables[key] ?? `{${key}}`));
}

export function createTranslator(language) {
    return (key, variables = {}) => interpolate(
        MESSAGES[language]?.[key] ?? MESSAGES.en[key] ?? key,
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
    t: createTranslator("en"),
});
