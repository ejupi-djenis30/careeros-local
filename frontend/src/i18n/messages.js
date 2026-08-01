import en from "./locales/en";
import it from "./locales/it";
import { SUPPORTED_LANGUAGES } from "./messageRegistry";

export { SUPPORTED_LANGUAGES };

// This eager aggregate is reserved for catalogue validation and test setup.
// Production code loads exactly one locale through messageRegistry.
export const MESSAGES = Object.freeze({ en, it });
