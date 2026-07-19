import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { I18nProvider } from "./I18nContext";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { useI18n } from "./useI18n";

function Probe() {
    const { t } = useI18n();
    return <p>{t("login.welcome")}</p>;
}

describe("I18nProvider", () => {
    beforeEach(() => {
        window.localStorage.clear();
        document.documentElement.lang = "";
    });

    it("starts in English and persists an explicit Italian choice locally", async () => {
        const user = userEvent.setup();
        render(<I18nProvider><LanguageSwitcher /><Probe /></I18nProvider>);

        expect(screen.getByText("Welcome back")).toBeInTheDocument();
        expect(document.documentElement).toHaveAttribute("lang", "en");

        await user.click(screen.getByRole("button", { name: "Italian" }));

        expect(screen.getByText("Bentornato")).toBeInTheDocument();
        expect(document.documentElement).toHaveAttribute("lang", "it");
        expect(window.localStorage.getItem("careeros.interface-language")).toBe("it");
    });
});
