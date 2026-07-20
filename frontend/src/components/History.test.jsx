import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { History } from "./History";
import { SearchService } from "../services/search";
import { I18nProvider } from "../i18n/I18nContext";
import { LanguageSwitcher } from "../i18n/LanguageSwitcher";
import { ToastProvider } from "../context/ToastContext";

vi.mock("../services/search", () => ({
    SearchService: { getProfiles: vi.fn() },
}));

describe("History localization lifecycle", () => {
    beforeEach(() => {
        window.localStorage.clear();
        SearchService.getProfiles.mockRejectedValue(new Error("offline"));
        vi.spyOn(console, "error").mockImplementation(() => {});
    });

    afterEach(() => vi.restoreAllMocks());

    it("retranslates a visible load error without repeating the request", async () => {
        render(
            <I18nProvider>
                <ToastProvider>
                    <LanguageSwitcher />
                    <History />
                </ToastProvider>
            </I18nProvider>,
        );

        expect(await screen.findAllByText("Failed to load search history.")).toHaveLength(2);
        expect(SearchService.getProfiles).toHaveBeenCalledTimes(1);

        fireEvent.click(screen.getByRole("button", { name: "Italian" }));

        expect(await screen.findAllByText("Impossibile caricare la cronologia delle ricerche.")).toHaveLength(2);
        await waitFor(() => expect(SearchService.getProfiles).toHaveBeenCalledTimes(1));
    });
});
