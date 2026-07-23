import { describe, expect, it } from "vitest";
import { createTranslator, translateMessage } from "./runtime";

describe("translateMessage", () => {
    it("renders the same semantic message in the active language", () => {
        const message = {
            messageKey: "schedules.toggleFailed",
            variables: { error: { messageKey: "common.unknownError" } },
        };

        expect(translateMessage(message, createTranslator("en"))).toBe(
            "Could not change the schedule: Unknown error",
        );
        expect(translateMessage(message, createTranslator("it"))).toBe(
            "Impossibile modificare la pianificazione: Errore sconosciuto",
        );
    });

    it("preserves raw service messages", () => {
        expect(translateMessage({ message: "Service unavailable" }, createTranslator("it"))).toBe(
            "Service unavailable",
        );
    });
});
