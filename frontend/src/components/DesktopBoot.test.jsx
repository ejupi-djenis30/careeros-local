import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { assertAccessible } from "../test/accessibility";
import { renderWithItalian as render } from "../test/renderWithI18n";
import { DesktopBoot } from "./DesktopBoot";

const bootstrapDesktop = vi.fn();
const reportDesktopReady = vi.fn();

vi.mock("../platform/desktop", () => ({
    bootstrapDesktop: (...args) => bootstrapDesktop(...args),
    reportDesktopReady: (...args) => reportDesktopReady(...args),
}));

describe("DesktopBoot accessibility", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        bootstrapDesktop.mockRejectedValue(new Error("Runtime locale non disponibile"));
        reportDesktopReady.mockResolvedValue(true);
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
        expect(reportDesktopReady).not.toHaveBeenCalled();
    });

    it("reports readiness only after the application tree is committed", async () => {
        bootstrapDesktop.mockResolvedValue({ desktop: true, state: "ready" });
        render(<DesktopBoot><p>Area privata</p></DesktopBoot>);

        expect(await screen.findByText("Area privata")).toBeInTheDocument();
        await waitFor(() => {
            expect(reportDesktopReady).toHaveBeenCalledTimes(1);
        });
    });
});
