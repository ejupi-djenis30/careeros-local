import { describe, expect, it } from "vitest";
import {
    canAccept,
    canCancel,
    canReject,
    canReview,
    filterWork,
    formatCopyablePrompt,
    GATE_DECISIONS,
    isTerminalState,
    proposalSupportsReview,
    workErrorMessage,
    WORK_KINDS,
    WORK_STATES,
} from "./agentWorkModel";

const translate = (key) => key;

describe("agentWorkModel", () => {
    it("defines the supported work kinds and states according to contract", () => {
        expect(WORK_KINDS).toEqual(["discover", "analyze", "materials"]);
        expect(WORK_STATES).toEqual([
            "queued",
            "returned",
            "accepted",
            "rejected",
            "canceled",
            "expired",
        ]);
        expect(GATE_DECISIONS).toEqual(["eligible", "hold", "reject"]);
    });

    it.each([
        ["grant_required", "agentWork.error.grantRequired"],
        ["grant_expired", "agentWork.error.grantExpired"],
        ["grant_revoked", "agentWork.error.grantRevoked"],
        ["scope_denied", "agentWork.error.scopeDenied"],
        ["work_not_found", "agentWork.error.workNotFound"],
        ["work_expired", "agentWork.error.workExpired"],
        ["work_canceled", "agentWork.error.workCanceled"],
        ["stale_input", "agentWork.error.staleInput"],
        ["invalid_result", "agentWork.error.invalidResult"],
        ["evidence_invalid", "agentWork.error.evidenceInvalid"],
        ["result_conflict", "agentWork.error.resultConflict"],
        ["revision_conflict", "agentWork.error.revisionConflict"],
        ["vault_unavailable", "agentWork.error.vaultUnavailable"],
        ["desktop_unavailable", "agentWork.error.desktopUnavailable"],
    ])("maps error code %s to friendly localized key", (code, expected) => {
        const error = { details: { detail: { code } } };
        expect(workErrorMessage(error, translate)).toBe(expected);
    });

    it("generates privacy-safe copyable prompt containing request UUID and tool names but no private data", () => {
        const request = {
            id: "550e8400-e29b-41d4-a716-446655440000",
            instructions: "Private confidential instructions here",
            user_private_email: "test@example.com",
        };
        const prompt = formatCopyablePrompt(request);
        expect(prompt).toContain("550e8400-e29b-41d4-a716-446655440000");
        expect(prompt).toContain("get_work_context");
        expect(prompt).toContain("submit_work_result");
        expect(prompt).not.toContain("Private confidential instructions");
        expect(prompt).not.toContain("test@example.com");
    });

    it("determines valid lifecycle actions based on state", () => {
        expect(canCancel({ state: "queued" })).toBe(true);
        expect(canCancel({ state: "returned" })).toBe(true);
        expect(canCancel({ state: "accepted" })).toBe(false);
        expect(canCancel({ state: "canceled" })).toBe(false);

        expect(canReview({ state: "returned" })).toBe(true);
        expect(canReview({ state: "queued" })).toBe(false);

        expect(canAccept({ state: "returned" })).toBe(true);
        expect(canAccept({ state: "accepted" })).toBe(false);

        expect(canReject({ state: "returned" })).toBe(true);
        expect(canReject({ state: "rejected" })).toBe(false);

        expect(isTerminalState({ state: "accepted" })).toBe(true);
        expect(isTerminalState({ state: "rejected" })).toBe(true);
        expect(isTerminalState({ state: "canceled" })).toBe(true);
        expect(isTerminalState({ state: "expired" })).toBe(true);
        expect(isTerminalState({ state: "queued" })).toBe(false);
        expect(isTerminalState({ state: "returned" })).toBe(false);
    });

    it("filters work items by state and query", () => {
        const items = [
            { id: "1", state: "queued", work_kind: "discover", instruction: "Find React jobs" },
            { id: "2", state: "returned", work_kind: "analyze", instruction: "Assess senior dev" },
            { id: "3", state: "accepted", work_kind: "materials", instruction: "Prepare CV" },
        ];

        expect(filterWork(items, { state: "all" })).toHaveLength(3);
        expect(filterWork(items, { state: "queued" })).toEqual([items[0]]);
        expect(filterWork(items, { query: "React" })).toEqual([items[0]]);
        expect(filterWork(items, { query: "analyze" })).toEqual([items[1]]);
    });

    it("blocks review when a returned payload uses legacy aliases or omits applied fields", () => {
        const work = { work_kind: "discover", state: "returned" };
        expect(proposalSupportsReview(work, {
            payload: {
                contract_version: 1,
                kind: "discover",
                listings: [{ external_url: "https://example.test/job", source_text: "Advert", gates: [], scores: {} }],
            },
        })).toBe(true);
        expect(proposalSupportsReview(work, {
            result: { contract_version: 1, kind: "discover", vacancies: [] },
        })).toBe(false);
        expect(proposalSupportsReview(work, {
            payload: { contract_version: 1, kind: "discover", listings: [{ external_url: "https://example.test/job" }] },
        })).toBe(false);
    });
});
