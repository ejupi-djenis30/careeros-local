import { render } from "@testing-library/react";

import { createTranslator, I18nContext } from "../i18n/runtime";

export function renderWithI18n(ui, options = {}) {
    const { language = "en", ...renderOptions } = options;
    const value = {
        language,
        setLanguage: () => {},
        t: createTranslator(language),
    };
    function I18nWrapper({ children }) {
        return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
    }

    return render(ui, { ...renderOptions, wrapper: I18nWrapper });
}

export function renderWithItalian(ui, options = {}) {
    return renderWithI18n(ui, { ...options, language: "it" });
}
