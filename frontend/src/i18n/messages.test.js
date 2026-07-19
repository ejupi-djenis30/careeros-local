import { describe, expect, it } from "vitest";

import { MESSAGES, SUPPORTED_LANGUAGES } from "./messages";
import { createTranslator } from "./runtime";

describe("message catalogue contract", () => {
    it("keeps the English and Italian catalogues in exact key parity", () => {
        const englishKeys = Object.keys(MESSAGES.en).sort();
        const italianKeys = Object.keys(MESSAGES.it).sort();

        expect(SUPPORTED_LANGUAGES).toEqual(["en", "it"]);
        expect(italianKeys).toEqual(englishKeys);
        for (const language of SUPPORTED_LANGUAGES) {
            for (const key of englishKeys) {
                expect(MESSAGES[language][key].trim(), `${language}.${key}`).not.toBe("");
            }
        }
    });

    it("translates and interpolates the search workflow in both languages", () => {
        const en = createTranslator("en");
        const it = createTranslator("it");

        expect(en("historyCard.lastDays", { count: 7 })).toBe("Last 7 days");
        expect(it("historyCard.lastDays", { count: 7 })).toBe("Ultimi 7 giorni");
        expect(en("searchProgress.analyzingTargetsCount", { current: 2, total: 5 })).toBe("Analyzing jobs (2/5)…");
        expect(it("searchProgress.analyzingTargetsCount", { current: 2, total: 5 })).toBe("Analisi annunci (2/5)…");
    });
});
