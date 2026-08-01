import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const registry = vi.hoisted(() => ({
    loadMessages: vi.fn(),
}));

vi.mock("./messageRegistry", () => ({
    SUPPORTED_LANGUAGES: Object.freeze(["en", "it"]),
    getMessages: () => null,
    hasMessages: () => false,
    loadMessages: registry.loadMessages,
}));

import { I18nProvider } from "./I18nContext";

describe("I18nProvider boot recovery", () => {
    beforeEach(() => {
        window.localStorage.clear();
        registry.loadMessages.mockReset();
        registry.loadMessages.mockRejectedValue(new Error("local chunk unavailable"));
    });

    it("shows localized recovery and retries only after an explicit action", async () => {
        window.localStorage.setItem("careeros.interface-language", "it");
        const user = userEvent.setup();
        render(<I18nProvider><div>workspace</div></I18nProvider>);

        const retry = await screen.findByRole("button", {
            name: "Riprova il caricamento della lingua",
        });
        expect(screen.getByRole("alert")).toHaveTextContent(
            "Non è stato possibile caricare la lingua locale dell’interfaccia.",
        );
        expect(registry.loadMessages.mock.calls.map(([language]) => language)).toEqual(["it", "en"]);
        await waitFor(() => expect(retry).toHaveFocus());

        await Promise.resolve();
        expect(registry.loadMessages).toHaveBeenCalledTimes(2);
        await user.click(retry);

        await waitFor(() => expect(registry.loadMessages).toHaveBeenCalledTimes(4));
        expect(registry.loadMessages.mock.calls.map(([language]) => language)).toEqual([
            "it",
            "en",
            "it",
            "en",
        ]);
        expect(await screen.findByRole("button", {
            name: "Riprova il caricamento della lingua",
        })).toHaveFocus();
    });
});
