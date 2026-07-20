import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "../lib/client";
import { ApplicationService } from "./applications";
import { ResumeService } from "./resumes";

describe("cancellable resource services", () => {
    afterEach(() => {
        vi.restoreAllMocks();
    });

    it("forwards request options when listing applications", async () => {
        const controller = new AbortController();
        const get = vi.spyOn(ApiClient, "get").mockResolvedValue([]);

        await ApplicationService.list({ signal: controller.signal });

        expect(get).toHaveBeenCalledWith("/applications", undefined, { signal: controller.signal });
    });

    it("forwards request options across resume reads", async () => {
        const controller = new AbortController();
        const options = { signal: controller.signal, suppressGlobalError: true };
        const get = vi.spyOn(ApiClient, "get").mockResolvedValue([]);

        await ResumeService.list(options);
        await ResumeService.listVersions(options);
        await ResumeService.get("resume/id", options);

        expect(get).toHaveBeenNthCalledWith(1, "/resumes", undefined, options);
        expect(get).toHaveBeenNthCalledWith(2, "/resumes/versions", undefined, options);
        expect(get).toHaveBeenNthCalledWith(3, "/resumes/resume%2Fid", undefined, options);
    });
});
