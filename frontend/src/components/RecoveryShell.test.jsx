import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { assertAccessible } from "../test/accessibility";
import { renderWithI18n as render } from "../test/renderWithI18n";
import { RecoveryShell } from "./RecoveryShell";

const state = vi.hoisted(() => ({
    session: { sessionState: "restore_pending", reauthRequired: false },
    archive: null,
    desktop: false,
    logout: vi.fn(),
    resetVault: vi.fn(),
    restoreArchive: vi.fn(),
    eraseLocalData: vi.fn(),
    clearRetryState: vi.fn(),
    openBackupWithNativeDialog: vi.fn(),
}));

vi.mock("../context/AuthContext", () => ({
    useAuth: () => ({
        logout: state.logout,
        maintenanceSession: state.session,
    }),
}));
vi.mock("../services/career", () => ({
    CareerService: { resetVault: (...args) => state.resetVault(...args) },
}));
vi.mock("../services/portability", () => ({
    PortabilityService: {
        restoreArchive: (...args) => state.restoreArchive(...args),
        eraseLocalData: (...args) => state.eraseLocalData(...args),
    },
}));
vi.mock("../services/vaultMaintenance", () => ({
    VaultMaintenance: {
        getRestoreArchive: () => state.archive,
        clearRetryState: (...args) => state.clearRetryState(...args),
    },
}));
vi.mock("../platform/desktop", () => ({
    isDesktopShell: () => state.desktop,
    openBackupWithNativeDialog: (...args) => state.openBackupWithNativeDialog(...args),
}));

describe("RecoveryShell", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        state.session = { sessionState: "restore_pending", reauthRequired: false };
        state.archive = null;
        state.desktop = false;
        state.logout.mockResolvedValue(true);
        state.resetVault.mockResolvedValue(null);
        state.restoreArchive.mockResolvedValue({ restored_files: 1 });
        state.eraseLocalData.mockResolvedValue({ files: 1, model_files: 0 });
    });

    it("moves focus to the recovery title when private content is replaced", async () => {
        render(<RecoveryShell />);

        const title = screen.getByRole("heading", { name: "Restore is incomplete" });
        await waitFor(() => expect(title).toHaveFocus());
        expect(title).toHaveAttribute("tabindex", "-1");
    });

    it("retries restore with the exact in-memory File without rendering its name", async () => {
        const user = userEvent.setup();
        const archive = new File(["PK"], "private-career-history.zip", {
            type: "application/zip",
        });
        state.archive = archive;
        const { container } = render(<RecoveryShell />);

        expect(screen.getByRole("heading", { name: "Restore is incomplete" })).toBeInTheDocument();
        expect(screen.queryByText("private-career-history.zip")).toBeNull();
        await user.click(screen.getByRole("button", {
            name: "Retry restore with the same backup",
        }));

        await waitFor(() => expect(state.restoreArchive).toHaveBeenCalledWith(archive));
        await assertAccessible(container);
    });

    it("asks for the same ZIP after restart and submits the selected File directly", async () => {
        const user = userEvent.setup();
        render(<RecoveryShell />);
        const archive = new File(["PK"], "same-private-backup.zip", {
            type: "application/zip",
        });

        expect(screen.getByRole("button", { name: "Choose the same backup ZIP" })).toBeInTheDocument();
        expect(screen.getByLabelText(/Same CareerOS backup ZIP/)).toHaveAttribute("tabindex", "-1");
        await user.upload(screen.getByLabelText(/Same CareerOS backup ZIP/), archive);

        await waitFor(() => expect(state.restoreArchive).toHaveBeenCalledWith(archive));
        expect(screen.queryByText("same-private-backup.zip")).toBeNull();
    });

    it("recovers from native picker failure without launching overlapping dialogs", async () => {
        state.desktop = true;
        let rejectPicker;
        state.openBackupWithNativeDialog.mockReturnValue(new Promise((_, reject) => {
            rejectPicker = reject;
        }));
        render(<RecoveryShell />);
        const choose = screen.getByRole("button", { name: "Choose the same backup ZIP" });

        choose.click();
        choose.click();
        expect(state.openBackupWithNativeDialog).toHaveBeenCalledTimes(1);
        await act(async () => {
            rejectPicker(new Error("native picker unavailable"));
            await Promise.resolve();
        });

        expect(await screen.findByRole("alert")).toHaveTextContent("Restore is still incomplete");
        await waitFor(() => expect(choose).toBeEnabled());
        expect(state.restoreArchive).not.toHaveBeenCalled();
    });

    it("returns to an enabled retry after cancelling the native picker", async () => {
        const user = userEvent.setup();
        state.desktop = true;
        state.openBackupWithNativeDialog.mockResolvedValue(null);
        render(<RecoveryShell />);
        const choose = screen.getByRole("button", { name: "Choose the same backup ZIP" });

        await user.click(choose);

        await waitFor(() => expect(choose).toBeEnabled());
        expect(state.restoreArchive).not.toHaveBeenCalled();
        expect(screen.queryByRole("alert")).toBeNull();
    });

    it.each(["reset_pending", "restore_pending"])(
        "offers exact-phrase erasure as a recovery superset for %s",
        async (sessionState) => {
            const user = userEvent.setup();
            state.session = { sessionState, reauthRequired: false };
            render(<RecoveryShell />);

            expect(screen.getByRole("button", {
                name: sessionState === "reset_pending"
                    ? "Retry vault reset"
                    : "Choose the same backup ZIP",
            })).toBeInTheDocument();

            const erase = screen.getByRole("button", { name: "Erase all local data" });
            expect(erase).toBeDisabled();
            await user.type(
                screen.getByLabelText(/To erase all managed local data/),
                "DELETE MY LOCAL DATA",
            );
            await user.click(erase);

            await waitFor(() => expect(state.eraseLocalData).toHaveBeenCalledTimes(1));
        },
    );

    it("shows only the direct erasure retry once erasure is pending", async () => {
        const user = userEvent.setup();
        state.session = { sessionState: "erasure_pending", reauthRequired: false };
        render(<RecoveryShell />);

        expect(screen.queryByRole("heading", { name: "Cannot finish this operation?" })).toBeNull();
        await user.click(screen.getByRole("button", { name: "Retry local data erasure" }));
        await waitFor(() => expect(state.eraseLocalData).toHaveBeenCalledTimes(1));
    });

    it("disables recovery operations after authority expiry and clears retry memory on relogin", async () => {
        const user = userEvent.setup();
        state.session = { sessionState: "restore_pending", reauthRequired: true };
        state.archive = new File(["PK"], "secret.zip", { type: "application/zip" });
        render(<RecoveryShell />);

        expect(screen.getByRole("status")).toHaveTextContent("Recovery access ended");
        expect(screen.queryByRole("button", { name: /Retry restore/ })).toBeNull();
        await user.click(screen.getByRole("button", { name: "Sign out and sign in again" }));

        expect(state.clearRetryState).toHaveBeenCalledTimes(1);
        expect(state.logout).toHaveBeenCalledWith({ force: true });
    });
});
