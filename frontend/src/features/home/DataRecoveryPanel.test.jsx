import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { assertAccessible } from "../../test/accessibility";
import { renderWithItalian as render } from "../../test/renderWithI18n";

import { PortabilityService } from "../../services/portability";
import { DataRecoveryPanel } from "./DataRecoveryPanel";

const platform = vi.hoisted(() => ({
    desktop: true,
    openBackupWithNativeDialog: vi.fn(),
    saveBackupWithNativeDialog: vi.fn(),
    verifyArchivePayload: vi.fn(),
}));
vi.mock("../../platform/desktop", () => ({
    isDesktopShell: () => platform.desktop,
    openBackupWithNativeDialog: platform.openBackupWithNativeDialog,
    saveBackupWithNativeDialog: platform.saveBackupWithNativeDialog,
    verifyArchivePayload: platform.verifyArchivePayload,
}));
vi.mock("../../services/portability", () => ({
    PortabilityService: {
        exportArchive: vi.fn(),
        inspectArchive: vi.fn(),
        restoreArchive: vi.fn(),
        eraseLocalData: vi.fn(),
    },
}));

const inspection = {
    status: "valid",
    archive_sha256: "a".repeat(64),
    archive_bytes: 4096,
    format_version: 4,
    created_at: "2026-07-24T10:30:00Z",
    record_counts: { profiles: 1, sources: 2 },
    total_records: 3,
    file_count: 2,
    file_bytes: 2048,
    compatible: true,
    restorable: false,
    verification_codes: [
        "manifest_verified",
        "members_verified",
        "records_verified",
        "relationships_verified",
        "file_bindings_verified",
    ],
    warning_codes: [
        "archive_not_encrypted",
        "archive_not_authenticated",
        "restore_requires_empty_vault",
    ],
};

describe("DataRecoveryPanel", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        platform.desktop = true;
        PortabilityService.exportArchive.mockResolvedValue({
            blob: new Blob(["archive"]),
            filename: "careeros-backup.zip",
            sha256: "a".repeat(64),
        });
        platform.openBackupWithNativeDialog.mockResolvedValue(
            new File(["PK"], "private-backup-name.zip", { type: "application/zip" }),
        );
        PortabilityService.inspectArchive.mockResolvedValue(inspection);
        PortabilityService.eraseLocalData.mockResolvedValue({
            files: 2,
            model_files: 3,
        });
        platform.saveBackupWithNativeDialog.mockResolvedValue({
            saved: true,
            sha256: "a".repeat(64),
            byteSize: 7,
        });
    });

    it("creates a backup with the native desktop dialog", async () => {
        const user = userEvent.setup();
        render(<DataRecoveryPanel hasProfile onErased={vi.fn()} />);

        await user.click(screen.getByRole("button", { name: /Crea backup/ }));

        await waitFor(() => expect(platform.saveBackupWithNativeDialog).toHaveBeenCalledTimes(1));
        expect(screen.getByRole("status")).toHaveTextContent("Backup verificato e salvato");
    });

    it("labels a browser download without claiming destination verification", async () => {
        const user = userEvent.setup();
        platform.desktop = false;
        const createObjectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:backup");
        const revokeObjectUrl = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
        const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
        render(<DataRecoveryPanel hasProfile onErased={vi.fn()} />);

        await user.click(screen.getByRole("button", { name: /Crea backup/ }));

        await waitFor(() => expect(platform.verifyArchivePayload).toHaveBeenCalledTimes(1));
        expect(createObjectUrl).toHaveBeenCalledTimes(1);
        expect(click).toHaveBeenCalledTimes(1);
        expect(revokeObjectUrl).toHaveBeenCalledWith("blob:backup");
        expect(screen.getByRole("status")).toHaveTextContent("non può verificare la destinazione finale");
    });

    it("verifies a backup without changing a populated vault and shows a content-free summary", async () => {
        const user = userEvent.setup();
        render(<DataRecoveryPanel hasProfile onErased={vi.fn()} />);

        await user.click(screen.getByRole("button", { name: /Scegli e verifica backup/ }));

        await waitFor(() => expect(PortabilityService.inspectArchive).toHaveBeenCalledTimes(1));
        expect(screen.getByRole("heading", { name: "Backup CareerOS valido" })).toBeInTheDocument();
        expect(screen.getByText("3")).toBeInTheDocument();
        expect(screen.getByText("2 file · 2 KB")).toBeInTheDocument();
        expect(screen.getByText(/Chiunque possieda il file/)).toBeInTheDocument();
        expect(screen.queryByText("private-backup-name.zip")).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Ripristina backup verificato" })).toBeDisabled();
        expect(screen.getByLabelText("File di backup CareerOS Local")).toHaveAttribute("tabindex", "-1");
    });

    it("reports a native picker failure and prevents overlapping dialogs", async () => {
        let rejectPicker;
        platform.openBackupWithNativeDialog.mockReturnValue(new Promise((_, reject) => {
            rejectPicker = reject;
        }));
        render(<DataRecoveryPanel hasProfile={false} />);
        const choose = screen.getByRole("button", { name: /Scegli e verifica backup/ });

        choose.click();
        choose.click();
        expect(platform.openBackupWithNativeDialog).toHaveBeenCalledTimes(1);
        await act(async () => {
            rejectPicker(new Error("Dialogo locale non disponibile"));
            await Promise.resolve();
        });

        expect(await screen.findByRole("status")).toHaveTextContent("Dialogo locale non disponibile");
        await waitFor(() => expect(choose).toBeEnabled());
        expect(PortabilityService.inspectArchive).not.toHaveBeenCalled();
    });

    it("enables a separate restore action only for a verified restorable backup", async () => {
        const user = userEvent.setup();
        PortabilityService.inspectArchive.mockResolvedValue({ ...inspection, restorable: true, warning_codes: [] });
        render(<DataRecoveryPanel hasProfile={false} onErased={vi.fn()} />);
        const restore = screen.getByRole("button", { name: "Ripristina backup verificato" });
        expect(restore).toBeDisabled();

        await user.click(screen.getByRole("button", { name: /Scegli e verifica backup/ }));

        await waitFor(() => expect(restore).toBeEnabled());
        expect(screen.getByText("Questo backup verificato è pronto per il ripristino.")).toBeInTheDocument();
        expect(PortabilityService.restoreArchive).not.toHaveBeenCalled();
    });

    it("does not render or refetch private state after terminal restore success", async () => {
        const user = userEvent.setup();
        PortabilityService.inspectArchive.mockResolvedValue({
            ...inspection,
            restorable: true,
            warning_codes: [],
        });
        PortabilityService.restoreArchive.mockResolvedValue({
            restored_files: 2,
            restored_records: { profiles: 1, sources: 2 },
        });
        render(<DataRecoveryPanel hasProfile={false} onErased={vi.fn()} />);

        await user.click(screen.getByRole("button", { name: /Scegli e verifica backup/ }));
        await user.click(await screen.findByRole("button", {
            name: "Ripristina backup verificato",
        }));

        await waitFor(() => expect(PortabilityService.restoreArchive).toHaveBeenCalledTimes(1));
        expect(screen.queryByRole("status")).toBeNull();
        expect(screen.getByRole("button", { name: "Ripristino…" })).toBeDisabled();
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
        expect(onErased).not.toHaveBeenCalled();
        expect(screen.queryByRole("status")).toBeNull();
    });

    it("passes the recovery accessibility and destructive-action keyboard gate", async () => {
        const user = userEvent.setup();
        const { container } = render(<main><h1>Recupero dati</h1><DataRecoveryPanel hasProfile onErased={vi.fn()} /></main>);

        await user.click(screen.getByRole("button", { name: /Scegli e verifica backup/ }));
        await screen.findByRole("heading", { name: "Backup CareerOS valido" });
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
