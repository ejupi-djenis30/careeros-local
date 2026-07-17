import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { assertAccessible } from "../test/accessibility";
import { DesktopBoot } from "./DesktopBoot";

const bootstrapDesktop = vi.fn();

vi.mock("../platform/desktop", () => ({
    bootstrapDesktop: (...args) => bootstrapDesktop(...args),
}));

describe("DesktopBoot accessibility", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        bootstrapDesktop.mockRejectedValue(new Error("Runtime locale non disponibile"));
    });

    it("announces setup recovery and exposes retry by keyboard", async () => {
        const user = userEvent.setup();
        const { container } = render(<DesktopBoot><p>Area privata</p></DesktopBoot>);

        const retry = await screen.findByRole("button", { name: "Riprova" });
        await assertAccessible(container);

        await user.tab();
        expect(retry).toHaveFocus();
        await user.keyboard("{Enter}");
        expect(bootstrapDesktop).toHaveBeenCalledTimes(2);
    });
});
