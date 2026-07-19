import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConfirmationDialog } from "./ConfirmationDialog";
import { renderWithI18n as render } from "../test/renderWithI18n";

function Fixture({ isOpen, onCancel }) {
  return (
    <>
      <button type="button">Origin</button>
      <ConfirmationDialog
        isOpen={isOpen}
        title="Erase vault?"
        message="This cannot be undone."
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />
    </>
  );
}

describe("ConfirmationDialog keyboard behavior", () => {
  it("moves focus safely, traps Tab, handles Escape, and restores focus", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    const { rerender } = render(<Fixture isOpen={false} onCancel={onCancel} />);
    const origin = screen.getByRole("button", { name: "Origin" });
    origin.focus();

    rerender(<Fixture isOpen onCancel={onCancel} />);

    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    const confirm = screen.getByRole("button", { name: "Confirm" });
    confirm.focus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledTimes(1);
    rerender(<Fixture isOpen={false} onCancel={onCancel} />);
    expect(origin).toHaveFocus();
  });
});
