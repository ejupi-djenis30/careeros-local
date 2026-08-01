import { SUPPORTED_LANGUAGES } from "./messageRegistry";
import { useI18n } from "./useI18n";

export function LanguageSwitcher() {
    const { language, setLanguage, pendingLanguage, languageError, t } = useI18n();
    return (
        <div
            className="language-switcher"
            role="group"
            aria-label={t("language.label")}
            aria-busy={pendingLanguage ? "true" : undefined}
        >
            {SUPPORTED_LANGUAGES.map((code) => (
                <button
                    key={code}
                    type="button"
                    className={language === code ? "is-active" : ""}
                    aria-pressed={language === code}
                    aria-label={t(`language.${code}`)}
                    title={t(`language.${code}`)}
                    disabled={Boolean(pendingLanguage)}
                    onClick={() => void setLanguage(code)}
                >
                    {code.toUpperCase()}
                </button>
            ))}
            {languageError && (
                <span className="visually-hidden" role="alert">{t("language.loadFailed")}</span>
            )}
        </div>
    );
}
