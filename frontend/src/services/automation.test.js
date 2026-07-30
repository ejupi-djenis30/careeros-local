import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiClient } from "../lib/client";
import { AutomationService } from "./automation";

describe("AutomationService", () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it("uses the authenticated grant-management endpoints", async () => {
        const get = vi.spyOn(ApiClient, "get").mockResolvedValue([]);
        const post = vi.spyOn(ApiClient, "post").mockResolvedValue({});
        const controller = new AbortController();

        await AutomationService.listGrants({ signal: controller.signal });
        await AutomationService.issueGrant({ label: "Codex" }, { signal: controller.signal });
        await AutomationService.revokeGrant("grant/id", "CurrentPassword1", {
            signal: controller.signal,
        });

        expect(get).toHaveBeenCalledWith(
            "/automation/grants",
            controller.signal,
            { suppressGlobalError: true },
        );
        expect(post).toHaveBeenNthCalledWith(
            1,
            "/automation/grants",
            { label: "Codex" },
            { signal: controller.signal, suppressGlobalError: true },
        );
        expect(post).toHaveBeenNthCalledWith(
            2,
            "/automation/grants/grant%2Fid/revoke",
            { password: "CurrentPassword1" },
            { signal: controller.signal, suppressGlobalError: true },
        );
    });
});
