import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Schedules } from "./Schedules";
import { SearchService } from "../services/search";
import { I18nProvider } from "../i18n/I18nContext";
import { LanguageSwitcher } from "../i18n/LanguageSwitcher";
import { ToastProvider } from "../context/ToastContext";

vi.mock("../services/search", () => ({
    SearchService: {
        getProfiles: vi.fn(),
        toggleSchedule: vi.fn(),
    },
}));

describe("Schedules localization lifecycle", () => {
    beforeEach(() => {
        window.localStorage.clear();
        SearchService.getProfiles.mockRejectedValue(new Error("offline"));
        vi.spyOn(console, "error").mockImplementation(() => {});
    });

    afterEach(() => vi.restoreAllMocks());

    it("retranslates inline and toast errors without repeating the request", async () => {
        render(
            <I18nProvider>
                <ToastProvider>
                    <LanguageSwitcher />
                    <Schedules />
                </ToastProvider>
            </I18nProvider>,
        );

        expect(await screen.findByText("Failed to load schedules.")).toBeInTheDocument();
        expect(screen.getByText("Failed to load schedules. Please refresh.")).toBeInTheDocument();
        expect(SearchService.getProfiles).toHaveBeenCalledTimes(1);

        fireEvent.click(screen.getByRole("button", { name: "Italian" }));

        expect(await screen.findByText("Impossibile caricare le pianificazioni.")).toBeInTheDocument();
        expect(screen.getByText("Impossibile caricare le pianificazioni. Aggiorna la pagina.")).toBeInTheDocument();
        await waitFor(() => expect(SearchService.getProfiles).toHaveBeenCalledTimes(1));
    });
});
