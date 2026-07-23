import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiClient } from "../lib/client";
import { PortabilityService } from "./portability";

describe("PortabilityService", () => {
    beforeEach(() => vi.restoreAllMocks());

    it("uses the verified archive endpoints and explicit erasure header", async () => {
        const download = vi.spyOn(ApiClient, "download").mockResolvedValue({});
        const postMultipart = vi.spyOn(ApiClient, "postMultipart").mockResolvedValue({});
        const remove = vi.spyOn(ApiClient, "delete").mockResolvedValue({});
        const file = new File(["PK"], "backup.zip", { type: "application/zip" });

        await PortabilityService.exportArchive();
        await PortabilityService.restoreArchive(file);
        await PortabilityService.eraseLocalData();

        expect(download).toHaveBeenCalledWith("/portability/export");
        expect(postMultipart.mock.calls[0][0]).toBe("/portability/restore");
        expect(postMultipart.mock.calls[0][1].get("file").name).toBe(file.name);
        expect(remove).toHaveBeenCalledWith("/portability/erase", expect.objectContaining({
            headers: { "X-Confirm-Erase": "ERASE-LOCAL-CAREER-DATA" },
        }));
    });
});
