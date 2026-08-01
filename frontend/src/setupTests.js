import '@testing-library/jest-dom';

import { MESSAGES, SUPPORTED_LANGUAGES } from "./i18n/messages";
import { registerMessages } from "./i18n/messageRegistry";

for (const language of SUPPORTED_LANGUAGES) {
    registerMessages(language, MESSAGES[language]);
}
