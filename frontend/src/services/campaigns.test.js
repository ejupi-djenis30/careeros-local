import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiClient } from "../lib/client";
import { CampaignService } from "./campaigns";

describe("CampaignService", () => {
    beforeEach(() => vi.restoreAllMocks());

    it("sends preview and import as bounded multipart requests", async () => {
        const postMultipart = vi.spyOn(ApiClient, "postMultipart").mockResolvedValue({});
        const file = new File(["PK"], "private-campaign.zip", { type: "application/zip" });

        await CampaignService.preview(file);
        await CampaignService.importArchive(file, {
            expectedFingerprint: "a".repeat(64),
            name: "Spring search",
            profileDisplayName: "Local profile",
        });

        const [previewPath, previewForm, previewOptions] = postMultipart.mock.calls[0];
        expect(previewPath).toBe("/campaigns/preview");
        expect(previewForm.get("archive")).toBe(file);
        expect(previewOptions).toEqual(expect.objectContaining({ timeoutMs: 120_000 }));

        const [importPath, importForm, importOptions] = postMultipart.mock.calls[1];
        expect(importPath).toBe("/campaigns/import");
        expect(importForm.get("archive")).toBe(file);
        expect(importForm.get("expected_fingerprint")).toBe("a".repeat(64));
        expect(importForm.get("name")).toBe("Spring search");
        expect(importForm.get("profile_display_name")).toBe("Local profile");
        expect(importOptions).toEqual(expect.objectContaining({ timeoutMs: 300_000 }));
    });

    it("omits optional import fields instead of serializing null-like values", async () => {
        const postMultipart = vi.spyOn(ApiClient, "postMultipart").mockResolvedValue({});
        const file = new File(["PK"], "campaign.zip", { type: "application/zip" });

        await CampaignService.importArchive(file, { expectedFingerprint: "b".repeat(64) });

        const form = postMultipart.mock.calls[0][1];
        expect(form.get("expected_fingerprint")).toBe("b".repeat(64));
        expect(form.has("name")).toBe(false);
        expect(form.has("profile_display_name")).toBe(false);
    });

    it("encodes read filters, identifiers, context and download boundaries", async () => {
        const get = vi.spyOn(ApiClient, "get").mockResolvedValue([]);
        const download = vi.spyOn(ApiClient, "download").mockResolvedValue({});
        const signal = new AbortController().signal;

        await CampaignService.list({ signal });
        await CampaignService.get("campaign/id", {
            query: "platform engineer",
            stage: "applied",
            priority: "High",
            limit: 25,
            offset: 5,
            signal,
        });
        await CampaignService.applicationContext("application/id", { signal });
        await CampaignService.downloadArtifact("campaign/id", "artifact/id");

        expect(get).toHaveBeenNthCalledWith(1, "/campaigns", signal, { signal });
        const detailUrl = new URL(`http://local${get.mock.calls[1][0]}`);
        expect(detailUrl.pathname).toBe("/campaigns/campaign%2Fid");
        expect(Object.fromEntries(detailUrl.searchParams)).toEqual({
            query: "platform engineer",
            stage: "applied",
            priority: "High",
            limit: "25",
            offset: "5",
        });
        expect(get).toHaveBeenNthCalledWith(
            3,
            "/applications/application%2Fid/campaign-context",
            signal,
            { signal },
        );
        expect(download).toHaveBeenCalledWith(
            "/campaigns/campaign%2Fid/artifacts/artifact%2Fid/download",
        );
    });
});
