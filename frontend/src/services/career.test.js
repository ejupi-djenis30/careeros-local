import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiClient } from "../lib/client";
import { CareerService } from "./career";
import { VaultMaintenance } from "./vaultMaintenance";

describe("CareerService reset recovery", () => {
    afterEach(() => vi.restoreAllMocks());

    it("retries reset without refresh and completes at the sign-in boundary", async () => {
        const remove = vi.spyOn(ApiClient, "delete").mockResolvedValue(null);
        const complete = vi.spyOn(VaultMaintenance, "complete").mockImplementation(() => {});

        await expect(CareerService.resetVault()).resolves.toBeNull();

        expect(remove).toHaveBeenCalledWith("/career-profile", {
            headers: { "X-Confirm-Delete": "DELETE-MY-CAREER-VAULT" },
            timeoutMs: 120_000,
            suppressGlobalError: true,
            suppressUnauthorizedRefresh: true,
        });
        expect(complete).toHaveBeenCalledTimes(1);
    });

    it("hands cleanup failure to the recovery state machine without completing", async () => {
        const error = new Error("reset pending");
        vi.spyOn(ApiClient, "delete").mockRejectedValue(error);
        const handleFailure = vi.spyOn(VaultMaintenance, "handleFailure").mockReturnValue(true);
        const complete = vi.spyOn(VaultMaintenance, "complete").mockImplementation(() => {});

        await expect(CareerService.resetVault()).rejects.toBe(error);

        expect(handleFailure).toHaveBeenCalledWith(error);
        expect(complete).not.toHaveBeenCalled();
    });
});
