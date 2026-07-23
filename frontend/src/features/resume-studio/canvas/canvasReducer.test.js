import { describe, expect, it } from "vitest";
import { resumeDraft } from "../../../test/fixtures";
import { canvasReducer, createCanvasState } from "./canvasReducer";

describe("canvasReducer", () => {
    it("tracks manual edits with bounded undo and redo", () => {
        const document = resumeDraft().canvas_document;
        const initial = createCanvasState(document);
        const edited = canvasReducer(initial, {
            type: "UPDATE_BLOCK",
            sectionId: "experience",
            blockId: document.sections[1].blocks[0].id,
            field: "title",
            value: "Staff Platform Engineer",
        });
        expect(edited.present.sections[1].blocks[0].content.title).toBe("Staff Platform Engineer");
        expect(edited.present.sections[1].blocks[0].manual_fields).toContain("title");
        expect(document.sections[1].blocks[0].content.title).toBe("Principal Engineer");

        const undone = canvasReducer(edited, { type: "UNDO" });
        expect(undone.present).toEqual(document);
        expect(canvasReducer(undone, { type: "REDO" }).present).toEqual(edited.present);
    });

    it("reorders sections and toggles visibility without mutating input", () => {
        const document = resumeDraft().canvas_document;
        let state = createCanvasState(document);
        state = canvasReducer(state, { type: "MOVE_SECTION", sectionId: "experience", direction: -1 });
        expect(state.present.sections.map((section) => section.id)).toEqual(["experience", "identity"]);
        state = canvasReducer(state, { type: "SET_SECTION_VISIBLE", sectionId: "experience", visible: false });
        expect(state.present.sections[0].visible).toBe(false);
        expect(document.sections[1].visible).toBe(true);
    });

    it("updates ATS-safe style tokens atomically", () => {
        const state = canvasReducer(createCanvasState(resumeDraft().canvas_document), {
            type: "SET_STYLE",
            field: "base_font_size",
            value: 11,
        });
        expect(state.present.style.base_font_size).toBe(11);
        expect(state.past).toHaveLength(1);
    });

    it("applies bounded block layout controls and keeps them undoable", () => {
        const document = resumeDraft().canvas_document;
        const blockId = document.sections[1].blocks[0].id;
        let state = canvasReducer(createCanvasState(document), {
            type: "SET_BLOCK_LAYOUT",
            sectionId: "experience",
            blockId,
            field: "spacing_before_pt",
            value: 99,
        });
        expect(state.present.sections[1].blocks[0].layout.spacing_before_pt).toBe(24);
        state = canvasReducer(state, {
            type: "SET_BLOCK_LAYOUT",
            sectionId: "experience",
            blockId,
            field: "keep_together",
            value: false,
        });
        expect(state.present.sections[1].blocks[0].layout.keep_together).toBe(false);
        expect(canvasReducer(state, { type: "UNDO" }).present.sections[1].blocks[0].layout.keep_together).not.toBe(false);
    });

    it("adds and removes a draft-only manual claim without inventing provenance", () => {
        const initial = createCanvasState(resumeDraft().canvas_document);
        const added = canvasReducer(initial, {
            type: "ADD_MANUAL_CLAIM",
            blockId: "manual-impact",
        });
        const achievement = added.present.sections.find((section) => section.kind === "achievement");
        expect(achievement.blocks[0]).toMatchObject({ id: "manual-impact", fact_ids: [] });

        const removed = canvasReducer(added, {
            type: "REMOVE_BLOCK",
            sectionId: "achievement",
            blockId: "manual-impact",
        });
        expect(removed.present.sections.some((section) => section.kind === "achievement")).toBe(false);
    });

    it("keeps 300-block edit operations below the 50ms local budget", () => {
        const document = resumeDraft().canvas_document;
        document.sections[1].blocks = Array.from({ length: 299 }, (_, index) => ({
            ...structuredClone(document.sections[1].blocks[0]),
            id: `performance-${index}`,
        }));
        let state = createCanvasState(document);
        const samples = [];
        for (let index = 0; index < 30; index += 1) {
            const started = performance.now();
            state = canvasReducer(state, {
                type: "UPDATE_BLOCK",
                sectionId: "experience",
                blockId: `performance-${index}`,
                field: "title",
                value: `Edited ${index}`,
            });
            samples.push(performance.now() - started);
        }
        samples.sort((left, right) => left - right);
        expect(samples[Math.ceil(samples.length * 0.95) - 1]).toBeLessThan(50);
    });
});
