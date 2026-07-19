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

export const I18nContext = createContext({
    language: "it",
    setLanguage: () => {},
    t: createTranslator("it"),
});
