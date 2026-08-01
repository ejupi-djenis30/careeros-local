import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiClient } from "../lib/client";
import { PortabilityService } from "./portability";
import { VaultMaintenance } from "./vaultMaintenance";

describe("PortabilityService", () => {
    beforeEach(() => {
        vi.restoreAllMocks();
        VaultMaintenance.clearRetryState();
    });

    it("uses the inspect and restore boundaries plus the explicit erasure header", async () => {
        const download = vi.spyOn(ApiClient, "download").mockResolvedValue({});
        const postMultipart = vi.spyOn(ApiClient, "postMultipart").mockResolvedValue({});
        const remove = vi.spyOn(ApiClient, "delete").mockResolvedValue({});
        const complete = vi.spyOn(VaultMaintenance, "complete").mockImplementation(() => {});
        const file = new File(["PK"], "backup.zip", { type: "application/zip" });

        await PortabilityService.exportArchive();
        await PortabilityService.inspectArchive(file);
        await PortabilityService.restoreArchive(file);
        await PortabilityService.eraseLocalData();

        expect(download).toHaveBeenCalledWith("/portability/export");
        expect(postMultipart.mock.calls[0][0]).toBe("/portability/inspect");
        expect(postMultipart.mock.calls[0][1].get("file").name).toBe(file.name);
        expect(postMultipart.mock.calls[0][2]).toEqual({ timeoutMs: 120_000 });
        expect(postMultipart.mock.calls[1][0]).toBe("/portability/restore");
        expect(postMultipart.mock.calls[1][1].get("file").name).toBe(file.name);
        expect(postMultipart.mock.calls[1][2]).toEqual({
            timeoutMs: 120_000,
            suppressGlobalError: true,
            suppressUnauthorizedRefresh: true,
        });
        expect(remove).toHaveBeenCalledWith("/portability/erase", expect.objectContaining({
            headers: { "X-Confirm-Erase": "ERASE-LOCAL-CAREER-DATA" },
            suppressGlobalError: true,
            suppressUnauthorizedRefresh: true,
        }));
        expect(complete).toHaveBeenCalledTimes(2);
    });

    it("keeps the current session when restore fails", async () => {
        vi.spyOn(ApiClient, "postMultipart").mockRejectedValue(new Error("restore failed"));
        const handleFailure = vi.spyOn(VaultMaintenance, "handleFailure").mockReturnValue(false);
        const complete = vi.spyOn(VaultMaintenance, "complete").mockImplementation(() => {});

        await expect(PortabilityService.restoreArchive(
            new File(["PK"], "backup.zip", { type: "application/zip" }),
        )).rejects.toThrow("restore failed");

        expect(handleFailure).toHaveBeenCalledTimes(1);
        expect(complete).not.toHaveBeenCalled();
    });

    it("retains the exact restore File before entering recovery-only mode", async () => {
        const file = new File(["PK"], "private-backup.zip", { type: "application/zip" });
        const error = {
            details: {
                detail: {
                    code: "restore_cleanup_pending",
                    session_state: "restore_pending",
                },
            },
        };
        vi.spyOn(ApiClient, "postMultipart").mockRejectedValue(error);
        const remember = vi.spyOn(VaultMaintenance, "rememberRestoreArchiveForFailure");
        const handleFailure = vi.spyOn(VaultMaintenance, "handleFailure").mockReturnValue(true);

        await expect(PortabilityService.restoreArchive(file)).rejects.toBe(error);

        expect(remember).toHaveBeenCalledWith(error, file);
        expect(remember.mock.invocationCallOrder[0]).toBeLessThan(
            handleFailure.mock.invocationCallOrder[0],
        );
    });

    it("does not retain a private archive for an inconsistent cleanup response", async () => {
        const file = new File(["PK"], "must-not-be-retained.zip", { type: "application/zip" });
        const error = {
            details: {
                detail: {
                    code: "restore_cleanup_pending",
                    session_state: "reset_pending",
                },
            },
        };
        vi.spyOn(ApiClient, "postMultipart").mockRejectedValue(error);
        vi.spyOn(VaultMaintenance, "handleFailure").mockReturnValue(false);

        await expect(PortabilityService.restoreArchive(file)).rejects.toBe(error);

        expect(VaultMaintenance.getRestoreArchive()).toBeNull();
    });
});
