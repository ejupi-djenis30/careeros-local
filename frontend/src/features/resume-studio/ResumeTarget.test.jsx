import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "../../lib/client";
import { careerProfile, resumeDraft, RESUME_ID } from "../../test/fixtures";
import { useResumeStudio } from "./useResumeStudio";

const { get, list, getProfile } = vi.hoisted(() => ({ get: vi.fn(), list: vi.fn(), getProfile: vi.fn() }));
vi.mock("../../services/resumes", () => ({ ResumeService: { get, list } }));
vi.mock("../../services/career", () => ({ CareerService: { getProfile } }));
vi.mock("../../context/ToastContext", () => ({ useToast: () => ({ showToast: vi.fn() }) }));
vi.mock("../../i18n/useI18n", () => ({ useI18n: () => ({ t: (key) => key }) }));
const otherId = "44444444-4444-4444-8444-444444444444";

beforeEach(() => {
    vi.resetAllMocks();
    getProfile.mockResolvedValue(careerProfile());
    list.mockResolvedValue([{ id: otherId }, { id: RESUME_ID }]);
    get.mockImplementation((id) => Promise.resolve(resumeDraft({ id })));
});

it("selects the exact linked draft even when it is not first in the library", async () => {
    const { result } = renderHook(() => useResumeStudio({ requestedResumeId: RESUME_ID }));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.draft.id).toBe(RESUME_ID);
    expect(get).toHaveBeenCalledTimes(1);
    expect(get.mock.calls[0][0]).toBe(RESUME_ID);
});

it.each(["", "../../private", "55555555-5555-4555-8555-555555555555"])("offers an explicit library fallback for invalid or absent target %s", async (requestedResumeId) => {
    const { result, rerender } = renderHook((props) => useResumeStudio(props), { initialProps: { requestedResumeId } });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.targetUnavailable).toBe(true);
    expect(result.current.draft).toBeNull();
    expect(get).not.toHaveBeenCalled();
    rerender({ requestedResumeId: null });
    await waitFor(() => expect(result.current.draft?.id).toBe(otherId));
    expect(result.current.targetUnavailable).toBe(false);
});

it("handles a target deleted after list retrieval without opening another draft", async () => {
    get.mockRejectedValue(new ApiError("Missing", { status: 404 }));
    const { result } = renderHook(() => useResumeStudio({ requestedResumeId: RESUME_ID }));
    await waitFor(() => expect(result.current.targetUnavailable).toBe(true));
    expect(result.current.draft).toBeNull();
});

it("ignores an earlier target response after the query changes", async () => {
    let finish;
    get.mockImplementation((id) => id === RESUME_ID ? new Promise((resolve) => { finish = resolve; }) : Promise.resolve(resumeDraft({ id })));
    const { result, rerender } = renderHook((props) => useResumeStudio(props), { initialProps: { requestedResumeId: RESUME_ID } });
    await waitFor(() => expect(finish).toBeTypeOf("function"));
    rerender({ requestedResumeId: otherId });
    await waitFor(() => expect(result.current.draft?.id).toBe(otherId));
    await act(async () => finish(resumeDraft()));
    expect(result.current.draft.id).toBe(otherId);
});
