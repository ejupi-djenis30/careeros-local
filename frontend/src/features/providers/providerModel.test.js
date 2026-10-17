import { describe, expect, it } from "vitest";

import {
    PRESERVE_SECRET,
    REDACTED_SECRET,
    advancedText,
    emptyProvider,
    payloadForSave,
    switchAdapter,
} from "./providerModel";

describe("providerModel", () => {
    it("preserves redacted secrets without putting their value back in the form", () => {
        const provider = {
            ...emptyProvider(),
            id: "8f4cd5cc-86e3-4a8d-a122-f57b98eea9fd",
            revision: 4,
            key: "example_jobs",
            display_name: "Example Jobs",
            request: {
                ...emptyProvider().request,
                base_url: "https://jobs.example.com",
                headers: { "X-API-Key": REDACTED_SECRET },
            },
        };

        const payload = payloadForSave(provider, {
            ...advancedText(provider),
            invalidJson: "invalid",
        });

        expect(payload.request.headers).toEqual({ "X-API-Key": PRESERVE_SECRET });
        expect(payload.expected_revision).toBe(4);
    });

    it("rejects malformed advanced JSON before any API mutation", () => {
        const provider = emptyProvider();

        expect(() => payloadForSave(provider, {
            ...advancedText(provider),
            headers: "[]",
            invalidJson: "Advanced JSON is invalid",
        })).toThrow("Advanced JSON is invalid");
    });

    it("switches between JSON paths and the supported HTML mapping shape", () => {
        const html = switchAdapter(emptyProvider(), "html");
        expect(html.extraction.items_path).toBeNull();
        expect(html.extraction.item_selector).toBe(".job");
        expect(html.extraction.fields.id.attribute).toBe("href");

        const json = switchAdapter(html, "json");
        expect(json.extraction.items_path).toBe("jobs");
        expect(json.extraction.item_selector).toBeNull();
        expect(json.extraction.fields.id.source).toBe("id");
    });
});
