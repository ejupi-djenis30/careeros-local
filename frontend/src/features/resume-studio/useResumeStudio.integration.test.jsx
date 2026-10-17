import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "../../lib/client";
import { CAREEROS_API_ERROR_EVENT } from "../../lib/events";
import { careerProfile, resumeDraft, RESUME_ID } from "../../test/fixtures";
import { useResumeStudio } from "./useResumeStudio";

vi.mock("../../context/ToastContext", () => ({ useToast: () => ({ showToast: vi.fn() }) }));
vi.mock("../../i18n/useI18n", () => ({ useI18n: () => ({ t: (key) => key }) }));

function json(value, status = 200) {
    return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

describe("resume request error ownership through the API client", () => {
    beforeEach(() => { vi.useFakeTimers(); ApiClient.invalidateSession(); });
    afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

    it.each([false, true])("keeps a save error local with navigation=%s", async (navigate) => {
        let finishSave;
        const saving = new Promise((resolve) => { finishSave = resolve; });
        const globalError = vi.fn();
        window.addEventListener(CAREEROS_API_ERROR_EVENT, globalError);
        const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((url, options) => {
            if (options.method === "PUT") return saving;
            if (url.endsWith("/career-profile")) return Promise.resolve(json(careerProfile()));
            if (url.endsWith("/resumes")) return Promise.resolve(json([resumeDraft()]));
            return Promise.resolve(json(resumeDraft()));
        });
        let view;
        try {
            await act(async () => { view = renderHook(() => useResumeStudio()); });
            act(() => { view.result.current.changeDraft({ title: "Pending write" }); });
            let operation;
            act(() => { operation = view.result.current.save(); });
            const writeOptions = fetchMock.mock.calls.find(([, options]) => options.method === "PUT")[1];
            if (navigate) act(() => { view.result.current.startNew(); });
            await act(async () => { finishSave(json({ detail: "Save rejected" }, 409)); await operation; });

            expect(globalError).not.toHaveBeenCalled();
            if (navigate) {
                expect(writeOptions.signal.aborted).toBe(true);
                expect(view.result.current.draft.id).toBeNull();
                expect(view.result.current.error).toBeNull();
            } else {
                expect(view.result.current.draft.id).toBe(RESUME_ID);
                expect(view.result.current.error).toEqual({ message: "Save rejected" });
                expect(view.result.current.dirty).toBe(true);
            }
        } finally {
            view?.unmount();
            window.removeEventListener(CAREEROS_API_ERROR_EVENT, globalError);
        }
    });

    it.each(["delete", "promote"])("keeps an acknowledged %s and its failed reconciliation local through the actual API client", async (action) => {
        vi.spyOn(window, "confirm").mockReturnValue(true);
        const globalError = vi.fn();
        let committed = false;
        let readsRecovered = false;
        window.addEventListener(CAREEROS_API_ERROR_EVENT, globalError);
        const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((url, options) => {
            if (options.method === "DELETE") {
                committed = true;
                return Promise.resolve(new Response(null, { status: 204 }));
            }
            if (options.method === "POST") {
                committed = true;
                return Promise.resolve(json(resumeDraft({ revision: 2 })));
            }
            if (url.endsWith("/career-profile")) return Promise.resolve(committed && action === "promote" && !readsRecovered
                ? json({ detail: "Synthetic profile unavailable" }, 503) : json(careerProfile()));
            if (url.endsWith("/resumes")) return Promise.resolve(committed && action === "delete" && !readsRecovered
                ? json({ detail: "Synthetic catalog unavailable" }, 503) : json(committed && action === "delete" ? [] : [resumeDraft()]));
            return Promise.resolve(json(resumeDraft()));
        });
        let view;
        try {
            await act(async () => { view = renderHook(() => useResumeStudio()); });
            await act(async () => { await (action === "delete" ? view.result.current.remove() : view.result.current.promoteClaim("synthetic-block")); });
            expect(view.result.current.refreshPending).toBe(true);
            if (action === "delete") expect(view.result.current.draft.id).toBeNull();
            else expect(view.result.current.draft.revision).toBe(2);
            expect(globalError).not.toHaveBeenCalled();
            readsRecovered = true;
            await act(async () => { await view.result.current.retryRefresh(); });
            expect(view.result.current.refreshPending).toBe(false);
            expect(fetchMock.mock.calls.filter(([, options]) => ["DELETE", "POST"].includes(options.method))).toHaveLength(1);
            expect(globalError).not.toHaveBeenCalled();
        } finally {
            view?.unmount();
            window.removeEventListener(CAREEROS_API_ERROR_EVENT, globalError);
        }
    });
});
