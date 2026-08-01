import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WorkspaceShell } from "./WorkspaceShell";
import { assertAccessible } from "../test/accessibility";
import { renderWithItalian as render } from "../test/renderWithI18n";

vi.mock("react-router", () => ({ useLocation: () => ({ pathname: "/" }) }));
vi.mock("../context/AuthContext", () => ({
    useAuth: () => ({ user: "mira", logout: vi.fn() }),
}));
vi.mock("../components/Layout/Sidebar", () => ({
    Sidebar: ({ isOpen, onClose, containerRef }) => (
        <div
            id="workspace-sidebar"
            ref={containerRef}
            data-open={isOpen}
            role={isOpen ? "dialog" : undefined}
            aria-modal={isOpen || undefined}
            aria-label="Navigazione principale"
        >
            <button type="button" onClick={onClose}>Chiudi menu laterale</button>
            <a href="#last-menu-item">Ultima voce</a>
            <button type="button" onClick={onClose}>Vai alle opportunità</button>
        </div>
    ),
}));

describe("WorkspaceShell mobile navigation", () => {
    const initialWidth = window.innerWidth;

    beforeEach(() => {
        Object.defineProperty(window, "innerWidth", {
            configurable: true,
            value: 390,
        });
        document.body.style.overflow = "clip";
    });

    afterEach(() => {
        Object.defineProperty(window, "innerWidth", {
            configurable: true,
            value: initialWidth,
        });
        document.body.style.overflow = "";
    });

    it("isolates the workspace, wraps focus and restores state after Escape", async () => {
        const user = userEvent.setup();
        render(<WorkspaceShell><p>Workspace content</p></WorkspaceShell>);
        const trigger = screen.getByRole("button", { name: "Apri menu" });
        const workspace = document.querySelector(".workspace-main");
        const skipLink = screen.getByRole("link", { name: "Vai al contenuto" });
        const scrim = document.querySelector(".workspace-scrim");

        expect(screen.getByRole("img", { name: "CareerOS Local" })).toBeInTheDocument();
        expect(trigger).toHaveAttribute("aria-controls", "workspace-sidebar");
        expect(trigger).toHaveAttribute("aria-expanded", "false");
        await user.click(trigger);

        expect(trigger).toHaveAttribute("aria-expanded", "true");
        expect(screen.getByRole("dialog", { name: "Navigazione principale" })).toHaveAttribute(
            "aria-modal",
            "true",
        );
        expect(workspace).toHaveAttribute("inert");
        expect(workspace).toHaveAttribute("aria-hidden", "true");
        expect(skipLink).toHaveAttribute("inert");
        expect(skipLink).toHaveAttribute("aria-hidden", "true");
        expect(document.body).toHaveStyle({ overflow: "hidden" });
        expect(scrim).toHaveAttribute("aria-hidden", "true");
        expect(scrim).toHaveAttribute("tabindex", "-1");
        await waitFor(() => expect(
            screen.getByRole("button", { name: "Chiudi menu laterale" }),
        ).toHaveFocus());
        await user.tab({ shift: true });
        expect(screen.getByRole("button", { name: "Vai alle opportunità" })).toHaveFocus();
        await user.tab();
        expect(screen.getByRole("button", { name: "Chiudi menu laterale" })).toHaveFocus();
        await assertAccessible(document.body);
        await user.keyboard("{Escape}");

        expect(trigger).toHaveAttribute("aria-expanded", "false");
        await waitFor(() => expect(trigger).toHaveFocus());
        expect(workspace).not.toHaveAttribute("inert");
        expect(workspace).not.toHaveAttribute("aria-hidden");
        expect(skipLink).not.toHaveAttribute("inert");
        expect(skipLink).not.toHaveAttribute("aria-hidden");
        expect(document.body).toHaveStyle({ overflow: "clip" });
    });

    it("closes on route activation and when the layout reaches desktop width", async () => {
        const user = userEvent.setup();
        render(<WorkspaceShell><p>Workspace content</p></WorkspaceShell>);
        const trigger = screen.getByRole("button", { name: "Apri menu" });

        await user.click(trigger);
        await user.click(screen.getByRole("button", { name: "Vai alle opportunità" }));
        expect(trigger).toHaveAttribute("aria-expanded", "false");
        await waitFor(() => expect(trigger).toHaveFocus());
        expect(document.body).toHaveStyle({ overflow: "clip" });

        await user.click(trigger);
        Object.defineProperty(window, "innerWidth", {
            configurable: true,
            value: 1200,
        });
        fireEvent(window, new Event("resize"));

        await waitFor(() => expect(trigger).toHaveAttribute("aria-expanded", "false"));
        await waitFor(() => expect(trigger).toHaveFocus());
        expect(document.body).toHaveStyle({ overflow: "clip" });
    });

    it("restores the prior body scroll state when the shell unmounts", async () => {
        const user = userEvent.setup();
        const view = render(<WorkspaceShell><p>Workspace content</p></WorkspaceShell>);

        await user.click(screen.getByRole("button", { name: "Apri menu" }));
        expect(document.body).toHaveStyle({ overflow: "hidden" });
        view.unmount();

        expect(document.body).toHaveStyle({ overflow: "clip" });
    });
});
