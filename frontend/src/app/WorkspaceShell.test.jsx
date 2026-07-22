import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceShell } from "./WorkspaceShell";
import { renderWithItalian as render } from "../test/renderWithI18n";

vi.mock("react-router-dom", () => ({ useLocation: () => ({ pathname: "/" }) }));
vi.mock("../context/AuthContext", () => ({
    useAuth: () => ({ user: "mira", logout: vi.fn() }),
}));
vi.mock("../components/Layout/Sidebar", () => ({
    Sidebar: ({ isOpen, onClose, containerRef }) => (
        <aside ref={containerRef} data-open={isOpen}>
            <button type="button" onClick={onClose}>Chiudi menu laterale</button>
            <a href="#last-menu-item">Ultima voce</a>
        </aside>
    ),
}));

describe("WorkspaceShell mobile navigation", () => {
    it("exposes menu state and restores trigger focus after Escape", async () => {
        const user = userEvent.setup();
        render(<WorkspaceShell><p>Workspace content</p></WorkspaceShell>);
        const trigger = screen.getByRole("button", { name: "Apri menu" });

        expect(screen.getByRole("img", { name: "CareerOS Local" })).toBeInTheDocument();
        expect(trigger).toHaveAttribute("aria-controls", "workspace-sidebar");
        expect(trigger).toHaveAttribute("aria-expanded", "false");
        await user.click(trigger);

        expect(trigger).toHaveAttribute("aria-expanded", "true");
        expect(screen.getByRole("button", { name: "Chiudi menu laterale" })).toHaveFocus();
        await user.keyboard("{Escape}");

        expect(trigger).toHaveAttribute("aria-expanded", "false");
        expect(trigger).toHaveFocus();
    });
});
