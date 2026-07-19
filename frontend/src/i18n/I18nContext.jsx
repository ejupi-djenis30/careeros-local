import { useCallback, useEffect, useMemo, useState } from "react";
import { SUPPORTED_LANGUAGES } from "./messages";
import { createTranslator, I18nContext as Context } from "./runtime";

const STORAGE_KEY = "careeros.interface-language";

function initialLanguage() {
    try {
        const saved = window.localStorage.getItem(STORAGE_KEY);
        return SUPPORTED_LANGUAGES.includes(saved) ? saved : "en";
    } catch {
        return "en";
    }
}

export function I18nProvider({ children }) {
    const [language, setLanguageState] = useState(initialLanguage);
    const setLanguage = useCallback((nextLanguage) => {
        if (!SUPPORTED_LANGUAGES.includes(nextLanguage)) return;
        setLanguageState(nextLanguage);
        try {
            window.localStorage.setItem(STORAGE_KEY, nextLanguage);
        } catch {
            // The selected language still applies for this session when storage is unavailable.
        }
    }, []);
    const t = useMemo(() => createTranslator(language), [language]);

    useEffect(() => {
        document.documentElement.lang = language;
    }, [language]);

    const value = useMemo(() => ({ language, setLanguage, t }), [language, setLanguage, t]);
    return <Context.Provider value={value}>{children}</Context.Provider>;
}
