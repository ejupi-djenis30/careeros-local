import { SUPPORTED_LANGUAGES } from "./messages";
import { useI18n } from "./useI18n";

export function LanguageSwitcher() {
    const { language, setLanguage, t } = useI18n();
    return (
        <div className="language-switcher" role="group" aria-label={t("language.label")}>
            {SUPPORTED_LANGUAGES.map((code) => (
                <button
                    key={code}
                    type="button"
                    className={language === code ? "is-active" : ""}
                    aria-pressed={language === code}
                    aria-label={t(`language.${code}`)}
                    title={t(`language.${code}`)}
                    onClick={() => setLanguage(code)}
                >
                    {code.toUpperCase()}
                </button>
            ))}
        </div>
    );
}
