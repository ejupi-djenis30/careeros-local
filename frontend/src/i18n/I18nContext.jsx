import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
    getMessages,
    hasMessages,
    loadMessages,
    SUPPORTED_LANGUAGES,
} from "./messageRegistry";
import { createTranslator, I18nContext as Context } from "./runtime";

const STORAGE_KEY = "careeros.interface-language";
const BOOT_COPY = Object.freeze({
    en: Object.freeze({
        loading: "Loading the private workspace…",
        failed: "The local interface language could not be loaded.",
        retry: "Retry language load",
    }),
    it: Object.freeze({
        loading: "Caricamento dello spazio di lavoro privato…",
        failed: "Non è stato possibile caricare la lingua locale dell’interfaccia.",
        retry: "Riprova il caricamento della lingua",
    }),
});

function initialLanguage() {
    try {
        const saved = window.localStorage.getItem(STORAGE_KEY);
        return SUPPORTED_LANGUAGES.includes(saved) ? saved : "en";
    } catch {
        return "en";
    }
}

export function I18nProvider({ children }) {
    const [requestedAtBoot] = useState(initialLanguage);
    const [language, setLanguageState] = useState(
        hasMessages(requestedAtBoot) ? requestedAtBoot : null,
    );
    const [pendingLanguage, setPendingLanguage] = useState(
        hasMessages(requestedAtBoot) ? null : requestedAtBoot,
    );
    const [languageError, setLanguageError] = useState(false);
    const [bootAttempt, setBootAttempt] = useState(0);
    const requestSequence = useRef(0);
    const mounted = useRef(true);
    const bootRetry = useRef(null);

    useEffect(() => {
        mounted.current = true;
        return () => {
            mounted.current = false;
            requestSequence.current += 1;
        };
    }, []);

    useEffect(() => {
        if (language) return undefined;
        const sequence = requestSequence.current + 1;
        requestSequence.current = sequence;
        let active = true;

        const prepare = async () => {
            let fallbackUsed = false;
            try {
                await loadMessages(requestedAtBoot);
                if (!active || !mounted.current || requestSequence.current !== sequence) return;
                setLanguageState(requestedAtBoot);
                setPendingLanguage(null);
            } catch {
                if (requestedAtBoot === "en") {
                    if (!active || !mounted.current || requestSequence.current !== sequence) return;
                    setPendingLanguage(null);
                    setLanguageError(true);
                    return;
                }
                try {
                    await loadMessages("en");
                    if (!active || !mounted.current || requestSequence.current !== sequence) return;
                    fallbackUsed = true;
                    setLanguageState("en");
                    setPendingLanguage(null);
                    setLanguageError(fallbackUsed);
                } catch {
                    if (!active || !mounted.current || requestSequence.current !== sequence) return;
                    setPendingLanguage(null);
                    setLanguageError(true);
                }
            }
        };
        void prepare();
        return () => {
            active = false;
        };
    }, [bootAttempt, language, requestedAtBoot]);

    const setLanguage = useCallback(async (nextLanguage) => {
        if (
            !SUPPORTED_LANGUAGES.includes(nextLanguage)
            || nextLanguage === language
            || pendingLanguage
        ) return false;

        if (hasMessages(nextLanguage)) {
            setLanguageError(false);
            setLanguageState(nextLanguage);
            try {
                window.localStorage.setItem(STORAGE_KEY, nextLanguage);
            } catch {
                // The selected language still applies for this session when storage is unavailable.
            }
            return true;
        }

        const sequence = requestSequence.current + 1;
        requestSequence.current = sequence;
        setPendingLanguage(nextLanguage);
        setLanguageError(false);
        try {
            await loadMessages(nextLanguage);
            if (!mounted.current || requestSequence.current !== sequence) return false;
            setLanguageState(nextLanguage);
            try {
                window.localStorage.setItem(STORAGE_KEY, nextLanguage);
            } catch {
                // The selected language still applies for this session when storage is unavailable.
            }
            return true;
        } catch {
            if (mounted.current && requestSequence.current === sequence) setLanguageError(true);
            return false;
        } finally {
            if (mounted.current && requestSequence.current === sequence) setPendingLanguage(null);
        }
    }, [language, pendingLanguage]);
    const t = useMemo(
        () => (language && getMessages(language) ? createTranslator(language) : null),
        [language],
    );

    useEffect(() => {
        document.documentElement.lang = language || requestedAtBoot;
    }, [language, requestedAtBoot]);

    useEffect(() => {
        if (language || !languageError || pendingLanguage) return undefined;
        const frame = window.requestAnimationFrame(() => bootRetry.current?.focus());
        return () => window.cancelAnimationFrame(frame);
    }, [language, languageError, pendingLanguage]);

    const retryBoot = useCallback(() => {
        if (language || pendingLanguage) return;
        setLanguageError(false);
        setPendingLanguage(requestedAtBoot);
        setBootAttempt((attempt) => attempt + 1);
    }, [language, pendingLanguage, requestedAtBoot]);

    const value = useMemo(
        () => ({ language, setLanguage, pendingLanguage, languageError, t }),
        [language, setLanguage, pendingLanguage, languageError, t],
    );

    if (!language || !t) {
        const copy = BOOT_COPY[requestedAtBoot];
        if (languageError) {
            return (
                <div className="localization-boot localization-boot--error" role="alert">
                    <strong>{copy.failed}</strong>
                    <button
                        ref={bootRetry}
                        type="button"
                        className="button button--primary"
                        onClick={retryBoot}
                    >
                        {copy.retry}
                    </button>
                </div>
            );
        }
        return (
            <div className="localization-boot" role="status">
                <span className="spinner-border" aria-hidden="true" />
                <span>{copy.loading}</span>
            </div>
        );
    }

    return <Context.Provider value={value}>{children}</Context.Provider>;
}
