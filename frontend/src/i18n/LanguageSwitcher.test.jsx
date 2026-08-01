import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { createTranslator, I18nContext } from "./runtime";
import { LanguageSwitcher } from "./LanguageSwitcher";

function renderSwitcher(overrides = {}) {
    const value = {
        language: "en",
        setLanguage: vi.fn(),
        pendingLanguage: null,
        languageError: false,
        t: createTranslator("en"),
        ...overrides,
    };
    return {
        ...render(
            <I18nContext.Provider value={value}>
                <LanguageSwitcher />
            </I18nContext.Provider>,
        ),
        value,
    };
}

describe("LanguageSwitcher", () => {
    it("exposes pressed state and a keyboard-focusable language choice", async () => {
        const user = userEvent.setup();
        const { value } = renderSwitcher();
        const english = screen.getByRole("button", { name: "English" });
        const italian = screen.getByRole("button", { name: "Italian" });

        expect(english).toHaveAttribute("aria-pressed", "true");
        expect(italian).toHaveAttribute("aria-pressed", "false");
        await user.tab();
        expect(english).toHaveFocus();
        await user.click(italian);
        expect(value.setLanguage).toHaveBeenCalledWith("it");
    });

    it("disables both controls and marks the group busy during a catalogue load", () => {
        renderSwitcher({ pendingLanguage: "it" });

        expect(screen.getByRole("group", { name: "Interface language" })).toHaveAttribute(
            "aria-busy",
            "true",
        );
        for (const button of screen.getAllByRole("button")) expect(button).toBeDisabled();
    });
});
