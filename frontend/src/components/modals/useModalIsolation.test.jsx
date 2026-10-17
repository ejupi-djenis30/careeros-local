import { StrictMode, useRef } from "react";
import { createPortal } from "react-dom";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmationDialog } from "../ConfirmationDialog";
import { DismissDialog } from "../JobTable/DismissDialog";
import { renderWithI18n as render } from "../../test/renderWithI18n";
import { useModalIsolation } from "./useModalIsolation";

const addedElements = [];
afterEach(() => {
    cleanup();
    addedElements.splice(0).forEach((element) => element.remove());
    document.body.style.overflow = "";
});

function Probe({ open, name = "Probe", wrapped = false, onClose, blocked, children, ...options }) {
    const dialogRef = useRef(null);
    useModalIsolation({
        isOpen: open,
        dialogRef,
        onRequestClose: onClose,
        closeBlocked: blocked,
        ...options,
    });
    if (!open) return null;
    const dialog = (
        <section ref={dialogRef} role="dialog" aria-label={name} tabIndex={-1}>
            {children ?? <><button>{name} first</button><button>{name} last</button></>}
        </section>
    );
    return createPortal(wrapped ? <div>{dialog}</div> : dialog, document.body);
}

function Confirmation({ open = true, title = "Confirmation", onClose = vi.fn() }) {
    return <ConfirmationDialog isOpen={open} title={title} message="Synthetic fixture"
        onCancel={onClose} onConfirm={vi.fn()} />;
}

describe("shared modal ownership with real dialog surfaces", () => {
    it("portals confirmations outside their isolated background", () => {
        const view = render(<><button>Background</button><Confirmation /></>);
        const dialog = screen.getByRole("dialog", { name: "Confirmation" });
        expect(view.container).toHaveAttribute("inert");
        expect(view.container).toHaveAttribute("aria-hidden", "true");
        expect(view.container).not.toContainElement(dialog);
        expect(dialog.closest("[inert]")).toBeNull();
    });

    it("closes only the top confirmation and returns focus inside the underlying dismiss dialog", () => {
        const lowerClose = vi.fn();
        const upperClose = vi.fn();
        const fixture = (upper) => <>
            <DismissDialog open jobTitle="Synthetic job" onClose={lowerClose} onDismiss={vi.fn()} />
            <Confirmation open={upper} title="Top confirmation" onClose={upperClose} />
        </>;
        const view = render(fixture(false));
        const lower = screen.getByRole("dialog");
        const lowerCancel = within(lower).getByRole("button", { name: "Cancel" });
        view.rerender(fixture(true));
        fireEvent.keyDown(document, { key: "Escape" });
        expect(upperClose).toHaveBeenCalledTimes(1);
        expect(lowerClose).not.toHaveBeenCalled();
        view.rerender(fixture(false));
        expect(lowerCancel).toHaveFocus();
        expect(lower.closest("[inert]")).toBeNull();
        expect(document.body.style.overflow).toBe("hidden");
    });

    it("keeps scroll locked when the lower real confirmation closes first", () => {
        document.body.style.overflow = "clip";
        const fixture = (lower, upper) => <>
            <Confirmation title="Lower" open={lower} />
            <Confirmation title="Upper" open={upper} />
        </>;
        const view = render(fixture(true, false));
        view.rerender(fixture(true, true));
        view.rerender(fixture(false, true));
        expect(screen.getByRole("dialog", { name: "Upper" })).toBeInTheDocument();
        expect(document.body.style.overflow).toBe("hidden");
        view.rerender(fixture(false, false));
        expect(document.body.style.overflow).toBe("clip");
    });

    it("inherits the original opener when an underlying modal unmounts out of order", () => {
        const fixture = (lower, upper) => <>
            <button>Origin</button><Probe name="Lower" open={lower} /><Probe name="Upper" open={upper} />
        </>;
        const view = render(fixture(false, false));
        const origin = screen.getByRole("button", { name: "Origin" });
        origin.focus();
        view.rerender(fixture(true, false));
        view.rerender(fixture(true, true));
        const upperFocus = screen.getByRole("button", { name: "Upper first" });
        view.rerender(fixture(false, true));
        expect(upperFocus).toHaveFocus();
        view.rerender(fixture(false, false));
        expect(origin).toHaveFocus();
    });
});

describe("modal state, focus and lifecycle boundaries", () => {
    it.each([false, true])("resolves the actual body portal root (wrapped=%s)", (wrapped) => {
        const view = render(<Probe open wrapped={wrapped} />);
        const dialog = screen.getByRole("dialog");
        expect(dialog.closest("[inert]")).toBeNull();
        expect(dialog.closest('[aria-hidden="true"]')).toBeNull();
        expect(view.container).toHaveAttribute("inert");
        expect(screen.getByRole("button", { name: "Probe first" })).toHaveFocus();
    });

    it("restores preexisting inert property/attribute, ARIA and overflow exactly", () => {
        const background = document.createElement("aside");
        background.setAttribute("inert", "existing-inert");
        background.setAttribute("aria-hidden", "false");
        Object.defineProperty(background, "inert", { configurable: true, writable: true, value: false });
        document.body.append(background);
        addedElements.push(background);
        document.body.style.overflow = "clip";
        const view = render(<Probe open />);
        expect(background.inert).toBe(true);
        expect(background).toHaveAttribute("aria-hidden", "true");
        view.unmount();
        expect(background.inert).toBe(false);
        expect(background).toHaveAttribute("inert", "existing-inert");
        expect(background).toHaveAttribute("aria-hidden", "false");
        expect(document.body.style.overflow).toBe("clip");
    });

    it("isolates later body portals and restores their state on final unmount", async () => {
        const view = render(<Probe open />);
        const late = document.createElement("button");
        late.setAttribute("aria-hidden", "false");
        document.body.append(late);
        addedElements.push(late);
        await waitFor(() => expect(late).toHaveAttribute("inert"));
        expect(late).toHaveAttribute("aria-hidden", "true");
        late.focus();
        expect(screen.getByRole("button", { name: "Probe first" })).toHaveFocus();
        view.unmount();
        expect(late).not.toHaveAttribute("inert");
        expect(late).toHaveAttribute("aria-hidden", "false");
    });

    it("filters hidden, disabled, negative-tabindex and hidden-ancestor controls when trapping Tab", async () => {
        const user = userEvent.setup();
        render(<Probe open>
            <button hidden>Hidden</button>
            <button style={{ visibility: "hidden" }}>Invisible</button>
            <div style={{ display: "none" }}><button>Hidden ancestor</button></div>
            <button aria-hidden="true">ARIA hidden</button>
            <button tabIndex={-1}>Programmatic</button>
            <fieldset disabled><button>Inherited disabled</button></fieldset>
            <input type="hidden" tabIndex={0} />
            <button disabled>Disabled</button>
            <button>Allowed first</button><button>Allowed last</button>
        </Probe>);
        const first = screen.getByRole("button", { name: "Allowed first" });
        const last = screen.getByRole("button", { name: "Allowed last" });
        expect(first).toHaveFocus();
        await user.tab({ shift: true });
        expect(last).toHaveFocus();
        await user.tab();
        expect(first).toHaveFocus();
        last.disabled = true;
        await user.tab();
        expect(first).toHaveFocus();
    });

    it("uses the dialog as fallback and discovers controls that appear later", async () => {
        const user = userEvent.setup();
        const view = render(<Probe open><p>No controls</p></Probe>);
        const dialog = screen.getByRole("dialog");
        expect(dialog).toHaveFocus();
        await user.tab();
        expect(dialog).toHaveFocus();
        view.rerender(<Probe open><button>Late control</button></Probe>);
        await user.tab();
        expect(screen.getByRole("button", { name: "Late control" })).toHaveFocus();
    });

    it("consumes blocked top Escape and reads updated close policy/callback without cascading", () => {
        const lower = vi.fn(), oldClose = vi.fn(), newClose = vi.fn(), backgroundHotkey = vi.fn();
        const fixture = (blocked, onClose) => <>
            <Probe name="Lower" open onClose={lower} /><Probe name="Top" open blocked={blocked} onClose={onClose} />
        </>;
        const view = render(fixture(true, oldClose));
        document.addEventListener("keydown", backgroundHotkey);
        try {
            fireEvent.keyDown(document, { key: "Escape" });
            expect(oldClose).not.toHaveBeenCalled();
            expect(lower).not.toHaveBeenCalled();
            expect(backgroundHotkey).not.toHaveBeenCalled();
            view.rerender(fixture(false, newClose));
            fireEvent.keyDown(document, { key: "Escape" });
            expect(newClose).toHaveBeenCalledTimes(1);
            expect(oldClose).not.toHaveBeenCalled();
            expect(lower).not.toHaveBeenCalled();
        } finally {
            document.removeEventListener("keydown", backgroundHotkey);
        }
    });

    it("preserves explicit background state and an explicit return-focus target", () => {
        const target = document.createElement("button");
        document.body.append(target);
        addedElements.push(target);
        const backgroundRef = { current: null };
        const fixture = (open) => <>
            <div ref={(element) => { backgroundRef.current = element; }} aria-hidden="false">Workspace</div>
            <Probe open={open} returnFocus={target} backgroundRef={backgroundRef} />
        </>;
        const view = render(fixture(false));
        const background = backgroundRef.current;
        view.rerender(fixture(true));
        expect(background).toHaveAttribute("inert");
        expect(background).toHaveAttribute("aria-hidden", "true");
        view.rerender(fixture(false));
        expect(background).not.toHaveAttribute("inert");
        expect(background).toHaveAttribute("aria-hidden", "false");
        expect(target).toHaveFocus();
    });

    it("balances StrictMode setup/cleanup and removes listeners on unmount", () => {
        const onClose = vi.fn();
        document.body.style.overflow = "clip";
        const view = render(<StrictMode><Probe open onClose={onClose} /></StrictMode>);
        fireEvent.keyDown(document, { key: "Escape" });
        expect(onClose).toHaveBeenCalledTimes(1);
        view.unmount();
        expect(view.container).not.toHaveAttribute("inert");
        expect(view.container).not.toHaveAttribute("aria-hidden");
        expect(document.body.style.overflow).toBe("clip");
        fireEvent.keyDown(document, { key: "Escape" });
        expect(onClose).toHaveBeenCalledTimes(1);
    });
});
