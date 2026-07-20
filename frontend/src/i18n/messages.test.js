import { describe, expect, it } from "vitest";

import { MESSAGES, SUPPORTED_LANGUAGES } from "./messages";
import { createTranslator } from "./runtime";

const SHARED_COPY_KEYS = new Set([
    "canvas.zoom",
    "data.privacy",
    "fact.type.link",
    "fact.type.portfolio",
    "factField.employment.freelance",
    "factField.url",
    "goal.actionKind.networking",
    "goal.actionKind.portfolio",
    "jobs.email",
    "login.password",
    "nav.vault",
    "page.home.eyebrow",
    "page.profile.title",
    "preferences.relocation.no",
    "profile.email",
    "resumeSection.portfolio",
    "stage.screening",
]);

function placeholders(message) {
    return [...message.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();
}

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

    it("keeps interpolation placeholders aligned across languages", () => {
        for (const key of Object.keys(MESSAGES.en)) {
            expect(placeholders(MESSAGES.it[key]), key).toEqual(placeholders(MESSAGES.en[key]));
        }
    });

    it("does not silently expose English copy in the Italian catalogue", () => {
        const sharedCopy = Object.keys(MESSAGES.en)
            .filter((key) => MESSAGES.en[key] === MESSAGES.it[key])
            .sort();

        expect(sharedCopy).toEqual([...SHARED_COPY_KEYS].sort());
    });

    it("translates and interpolates the search workflow in both languages", () => {
        const en = createTranslator("en");
        const it = createTranslator("it");

        expect(en("progressPage.state.reserved")).toBe("preparing");
        expect(it("progressPage.state.reserved")).toBe("in preparazione");
        expect(en("historyCard.lastDays", { count: 7 })).toBe("Last 7 days");
        expect(it("historyCard.lastDays", { count: 7 })).toBe("Ultimi 7 giorni");
        expect(en("searchProgress.analyzingTargetsCount", { current: 2, total: 5 })).toBe("Analyzing jobs (2/5)…");
        expect(it("searchProgress.analyzingTargetsCount", { current: 2, total: 5 })).toBe("Analisi annunci (2/5)…");
    });
});
