import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { Sidebar } from "./Sidebar";
import { renderWithItalian as render } from "../../test/renderWithI18n";

vi.mock("../../features/local-model/LocalModelStatus", () => ({
    LocalModelStatus: () => <div>Stato modello</div>,
}));
vi.mock("../../i18n/LanguageSwitcher", () => ({
    LanguageSwitcher: () => <div>Lingua</div>,
}));

function sidebar(isOpen, onClose = vi.fn()) {
    return (
        <MemoryRouter>
            <Sidebar
                username="mira"
                onLogout={vi.fn()}
                isOpen={isOpen}
                onClose={onClose}
                containerRef={{ current: null }}
            />
        </MemoryRouter>
    );
}

describe("Sidebar modal navigation semantics", () => {
    it("is modal only while open and closes when a route is activated", async () => {
        const user = userEvent.setup();
        const onClose = vi.fn();
        const view = render(sidebar(true, onClose));

        const drawer = screen.getByRole("dialog", { name: "Navigazione principale" });
        expect(drawer).toHaveAttribute("aria-modal", "true");

        await user.click(screen.getByRole("link", { name: "Annunci" }));
        expect(onClose).toHaveBeenCalledTimes(1);

        view.rerender(sidebar(false, onClose));
        expect(
            screen.getByRole("complementary", { name: "Navigazione principale" }),
        ).not.toHaveAttribute("aria-modal");
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
});
