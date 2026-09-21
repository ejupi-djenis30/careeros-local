import { describe, expect, it } from "vitest";
import { resumeWritePayload } from "./resumeModel";

describe("resumeWritePayload", () => {
    it("drops only deselected fact overrides so an explicit fact removal can save", () => {
        const draft = { id: "draft", revision: 3, title: "Reviewed draft", template_kind: "ats",
            selected_fact_ids: ["kept"], photo_asset_id: "remembered-photo",
            content_overrides: { kept: { title: "Approved wording" }, removed: { title: "Previously edited" } } };
        const payload = resumeWritePayload(draft);
        expect(payload.content_overrides).toEqual({ kept: { title: "Approved wording" } });
        expect(payload.selected_fact_ids).toEqual(["kept"]);
        expect(payload.expected_revision).toBe(3);
        expect(payload.photo_asset_id).toBeNull();
        expect(draft.content_overrides.removed.title).toBe("Previously edited");
        expect(draft.photo_asset_id).toBe("remembered-photo");
    });
});
