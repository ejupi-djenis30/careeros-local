import en from "./locales/en";
import it from "./locales/it";
import providerEn from "../features/providers/locales/providers-en";
import providerIt from "../features/providers/locales/providers-it";
import { SUPPORTED_LANGUAGES } from "./messageRegistry";

export { SUPPORTED_LANGUAGES };

// This eager aggregate is reserved for catalogue validation and test setup.
// Production code loads exactly one locale through messageRegistry.
export const MESSAGES = Object.freeze({
    en: Object.freeze({ ...en, ...providerEn }),
    it: Object.freeze({ ...it, ...providerIt }),
});
