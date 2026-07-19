import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { assertAccessible } from "../../test/accessibility";
import { renderWithItalian as render } from "../../test/renderWithI18n";

import { PortabilityService } from "../../services/portability";
import { DataRecoveryPanel } from "./DataRecoveryPanel";

const { saveBackupWithNativeDialog } = vi.hoisted(() => ({
    saveBackupWithNativeDialog: vi.fn(),
}));
vi.mock("../../platform/desktop", () => ({
    isDesktopShell: () => true,
    openBackupWithNativeDialog: vi.fn(),
    saveBackupWithNativeDialog,
}));
vi.mock("../../services/portability", () => ({
    PortabilityService: {
        exportArchive: vi.fn(),
        restoreArchive: vi.fn(),
        eraseLocalData: vi.fn(),
    },
}));

describe("DataRecoveryPanel", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        PortabilityService.exportArchive.mockResolvedValue({
            blob: new Blob(["archive"]),
            filename: "careeros-backup.zip",
        });
        PortabilityService.eraseLocalData.mockResolvedValue({
            files: 2,
            model_files: 3,
        });
        saveBackupWithNativeDialog.mockResolvedValue(true);
    });

    it("creates a backup with the native desktop dialog", async () => {
        const user = userEvent.setup();
        render(<DataRecoveryPanel hasProfile onErased={vi.fn()} />);

        await user.click(screen.getByRole("button", { name: /Crea backup/ }));

        await waitFor(() => expect(saveBackupWithNativeDialog).toHaveBeenCalledTimes(1));
        expect(screen.getByRole("status")).toHaveTextContent("Backup verificato e salvato");
    });

    it("requires the exact phrase before erasing managed local data", async () => {
        const user = userEvent.setup();
        const onErased = vi.fn();
        render(<DataRecoveryPanel hasProfile onErased={onErased} />);
        const erase = screen.getByRole("button", { name: "Cancella dati" });
        expect(erase).toBeDisabled();

        await user.type(screen.getByLabelText(/Per cancellare vault/), "CANCELLA I MIEI DATI");
        await user.click(erase);

        await waitFor(() => expect(PortabilityService.eraseLocalData).toHaveBeenCalledTimes(1));
        expect(onErased).toHaveBeenCalledTimes(1);
        expect(screen.getByRole("status")).toHaveTextContent("Rimossi 5 file gestiti");
    });

    it("passes the recovery accessibility and destructive-action keyboard gate", async () => {
        const user = userEvent.setup();
        const { container } = render(<main><h1>Recupero dati</h1><DataRecoveryPanel hasProfile onErased={vi.fn()} /></main>);

        await assertAccessible(container);
        const phrase = screen.getByLabelText(/Per cancellare vault/);
        phrase.focus();
        await user.keyboard("CANCELLA I MIEI DATI");
        await user.tab();
        const erase = screen.getByRole("button", { name: "Cancella dati" });
        expect(erase).toHaveFocus();
        await user.keyboard("{Enter}");
        await waitFor(() => expect(PortabilityService.eraseLocalData).toHaveBeenCalledTimes(1));
    });
});
