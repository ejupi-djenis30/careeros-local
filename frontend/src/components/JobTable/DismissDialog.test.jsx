import { useState } from "react";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { assertAccessible } from "../../test/accessibility";
import { renderWithI18n } from "../../test/renderWithI18n";
import { DismissDialog } from "./DismissDialog";

function Fixture() {
    const [open, setOpen] = useState(false);
    return (
        <>
            <button type="button" onClick={() => setOpen(true)}>Open dismiss dialog</button>
            <DismissDialog
                open={open}
                jobTitle="Platform Engineer"
                onDismiss={vi.fn()}
                onClose={() => setOpen(false)}
            />
        </>
    );
}

describe("DismissDialog", () => {
    afterEach(() => {
        document.body.style.overflow = "";
    });

    it("traps focus, closes with Escape, and restores the previous focus", async () => {
        const user = userEvent.setup();
        document.body.style.overflow = "clip";
        renderWithI18n(<Fixture />);

        const trigger = screen.getByRole("button", { name: "Open dismiss dialog" });
        await user.click(trigger);

        const dialog = screen.getByRole("dialog", { name: "Not interested in this job?" });
        expect(dialog).toHaveAttribute("aria-modal", "true");
        expect(dialog).toHaveAccessibleDescription("Choose a reason:");
        await assertAccessible(document.body);

        const cancel = within(dialog).getByRole("button", { name: "Cancel" });
        const close = within(dialog).getByRole("button", { name: "Close" });
        expect(cancel).toHaveFocus();
        expect(document.body).toHaveStyle({ overflow: "hidden" });

        await user.tab();
        expect(close).toHaveFocus();
        await user.tab({ shift: true });
        expect(cancel).toHaveFocus();

        await user.keyboard("{Escape}");
        await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
        expect(document.body).toHaveStyle({ overflow: "clip" });
        expect(trigger).toHaveFocus();
    });

    it("exposes localized semantics and keeps the dismissal value stable", async () => {
        const user = userEvent.setup();
        const onDismiss = vi.fn();
        renderWithI18n(
            <DismissDialog
                open
                jobTitle="Platform Engineer"
                onDismiss={onDismiss}
                onClose={vi.fn()}
            />,
            { language: "it" },
        );

        const dialog = screen.getByRole("dialog", { name: "Questo annuncio non ti interessa?" });
        expect(dialog).toHaveAccessibleDescription("Scegli un motivo:");
        await user.click(within(dialog).getByRole("button", { name: "Settore non adatto" }));

        expect(onDismiss).toHaveBeenCalledWith("wrong_domain");
    });
});
