import { describe, expect, it } from "vitest";
import { mergePreferenceCandidates, PreferenceCandidateError } from "./preferenceCandidates";

describe("mergePreferenceCandidates", () => {
    it("merges lists without duplicates and replaces one selected scalar", () => {
        const result = mergePreferenceCandidates(
            { target_roles: ["Developer"], workload_min: 60 },
            [
                { field: "target_roles", value: ["Developer", "Architect"] },
                { field: "workload_min", value: 80 },
            ],
        );
        expect(result).toEqual({ target_roles: ["Developer", "Architect"], workload_min: 80 });
    });

    it("rejects the complete merged value above the backend list limit", () => {
        const roles = Array.from({ length: 50 }, (_, index) => `Role ${index}`);
        expect(() => mergePreferenceCandidates(
            { target_roles: roles },
            [{ field: "target_roles", value: ["Overflow role"] }],
        )).toThrow(expect.objectContaining({ code: "limit", field: "target_roles" }));
    });

    it("requires an explicit choice between conflicting scalar candidates", () => {
        expect(() => mergePreferenceCandidates({}, [
            { field: "workload_min", value: 80 },
            { field: "workload_min", value: 20 },
        ])).toThrow(expect.objectContaining({ code: "scalarConflict", field: "workload_min" }));
    });

    it("validates cross-field combinations after merging with current preferences", () => {
        expect(() => mergePreferenceCandidates(
            { workload_max: 60 },
            [{ field: "workload_min", value: 80 }],
        )).toThrow(PreferenceCandidateError);
    });
});
