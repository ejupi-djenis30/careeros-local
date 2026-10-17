import { act, renderHook } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CareerService } from "../../services/career";
import { ResumeService } from "../../services/resumes";
import { careerProfile, FACT_ID, resumeDraft, RESUME_ID } from "../../test/fixtures";
import { useResumeStudio } from "./useResumeStudio";

const showToast = vi.hoisted(() => vi.fn());
vi.mock("../../context/ToastContext", () => ({ useToast: () => ({ showToast }) }));
vi.mock("../../i18n/useI18n", () => ({ useI18n: () => ({ t: (key) => key }) }));
vi.mock("../../services/career", () => ({ CareerService: { getProfile: vi.fn(), uploadPhoto: vi.fn() } }));
vi.mock("../../services/resumes", () => ({
    ResumeService: {
        list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), publish: vi.fn(),
        generate: vi.fn(), duplicate: vi.fn(), promoteClaim: vi.fn(), sync: vi.fn(),
        remove: vi.fn(), compareVersions: vi.fn(), restoreVersion: vi.fn(),
    },
}));

const REQUEST_OPTIONS = expect.objectContaining({ signal: expect.any(AbortSignal), suppressGlobalError: true });
const OTHER_ID = "88888888-8888-4888-8888-888888888888";
const otherDraft = () => resumeDraft({ id: OTHER_ID, title: "Other draft", revision: 8 });

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((resolvePromise, rejectPromise) => {
        resolve = resolvePromise;
        reject = rejectPromise;
    });
    return { promise, resolve, reject };
}

async function openStudio() {
    let view;
    await act(async () => { view = renderHook(() => useResumeStudio()); });
    expect(view.result.current.loading).toBe(false);
    expect(view.result.current.draft.id).toBe(RESUME_ID);
    return view;
}

describe("useResumeStudio asynchronous document ownership", () => {
    beforeEach(() => {
        vi.useFakeTimers();
        vi.resetAllMocks();
        vi.spyOn(window, "confirm").mockReturnValue(true);
        CareerService.getProfile.mockResolvedValue(careerProfile());
        ResumeService.list.mockResolvedValue([resumeDraft(), otherDraft()]);
        ResumeService.get.mockImplementation((id) => Promise.resolve(id === OTHER_ID ? otherDraft() : resumeDraft()));
        ResumeService.update.mockImplementation((id, data) => Promise.resolve(resumeDraft({ ...data, id, revision: 2 })));
        ResumeService.create.mockResolvedValue(resumeDraft());
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.restoreAllMocks();
    });

    it("selects only the latest load and keeps its pending status when an older load fails", async () => {
        const { result } = await openStudio();
        const first = deferred();
        const second = deferred();
        ResumeService.get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
        let firstLoad;
        let secondLoad;
        act(() => { firstLoad = result.current.loadDraft(RESUME_ID); });
        const firstSignal = ResumeService.get.mock.calls.at(-1)[1].signal;
        act(() => { secondLoad = result.current.loadDraft(OTHER_ID); });
        expect(firstSignal.aborted).toBe(true);

        await act(async () => { first.reject(new Error("Old load failure")); await firstLoad; });
        expect(result.current.busy).toBe("load");
        expect(result.current.error).toBeNull();
        await act(async () => { second.resolve(otherDraft()); await secondLoad; });
        expect(result.current.draft).toMatchObject({ id: OTHER_ID, revision: 8 });
        expect(result.current.busy).toBe("");
    });

    it("ignores an older successful load after the selected draft has loaded", async () => {
        const { result } = await openStudio();
        const pending = deferred();
        ResumeService.get.mockReturnValueOnce(pending.promise);
        let olderLoad;
        act(() => { olderLoad = result.current.loadDraft(RESUME_ID); });
        await act(async () => { await result.current.loadDraft(OTHER_ID); });
        await act(async () => { pending.resolve(resumeDraft()); await olderLoad; });
        expect(result.current.draft.id).toBe(OTHER_ID);
        expect(result.current.busy).toBe("");
    });

    it("keeps a new unsaved draft independent from an older autosave", async () => {
        const { result } = await openStudio();
        const pending = deferred();
        ResumeService.update.mockReturnValueOnce(pending.promise);
        act(() => { result.current.changeDraft({ title: "Old draft edited" }); });
        await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
        expect(result.current.busy).toBe("autosave");
        act(() => { result.current.startNew(); });
        act(() => { result.current.changeDraft({ title: "New unsaved work" }); });

        await act(async () => { pending.resolve(resumeDraft({ title: "Old draft edited", revision: 2 })); });
        expect(result.current.draft).toMatchObject({ id: null, revision: null, title: "New unsaved work" });
        expect(result.current).toMatchObject({ dirty: true, busy: "", error: null, autosaveState: "pending" });
        await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
        expect(ResumeService.create).toHaveBeenCalledWith(expect.objectContaining({ title: "New unsaved work" }), REQUEST_OPTIONS);
        expect(ResumeService.update).toHaveBeenCalledTimes(1);
    });

    it("preserves edits made while saving the same draft and uses its returned revision", async () => {
        const { result } = await openStudio();
        const pending = deferred();
        ResumeService.update.mockReturnValueOnce(pending.promise);
        act(() => { result.current.changeDraft({ title: "Saved snapshot" }); });
        let saving;
        act(() => { saving = result.current.save(); });
        act(() => { result.current.changeDraft({ title: "Newer local title", selected_fact_ids: [FACT_ID] }); });
        await act(async () => {
            pending.resolve(resumeDraft({ title: "Saved snapshot", revision: 2 }));
            await saving;
        });
        expect(result.current.draft).toMatchObject({ id: RESUME_ID, revision: 2, title: "Newer local title", selected_fact_ids: [FACT_ID] });
        expect(result.current.dirty).toBe(true);
        await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
        expect(ResumeService.update).toHaveBeenLastCalledWith(RESUME_ID, expect.objectContaining({
            title: "Newer local title", expected_revision: 2, selected_fact_ids: [FACT_ID],
        }), REQUEST_OPTIONS);
    });

    const actions = [
        ["save", "update", []],
        ["publish", "publish", []],
        ["generateFromProfile", "generate", []],
        ["duplicate", "duplicate", []],
        ["promoteClaim", "promoteClaim", ["claim"]],
        ["reviewSync", "sync", []],
        ["applySync", "sync", []],
        ["remove", "remove", []],
        ["compareVersions", "compareVersions", [["one", "two"]]],
        ["restoreVersion", "restoreVersion", [{ id: "one", name: "Version" }]],
    ];

    it.each(actions)("ignores a delayed %s result after another draft is selected", async (action, service, args) => {
        const { result } = await openStudio();
        const pending = deferred();
        ResumeService[service].mockReturnValueOnce(pending.promise);
        if (action === "save") act(() => { result.current.changeDraft({ title: "Pending save" }); });
        let operation;
        await act(async () => { operation = result.current[action](...args); });
        await act(async () => { await result.current.loadDraft(OTHER_ID); });
        await act(async () => { pending.resolve({ ...resumeDraft({ revision: 99 }), draft: resumeDraft() }); await operation; });

        expect(result.current.draft).toMatchObject({ id: OTHER_ID, title: "Other draft", revision: 8 });
        expect(result.current).toMatchObject({ dirty: false, busy: "", error: null, autosaveState: "idle", syncPreview: null, versionComparison: null });
        expect(showToast).not.toHaveBeenCalled();
    });

    it.each(actions)("ignores a delayed %s error after a new draft is started", async (action, service, args) => {
        const { result } = await openStudio();
        const pending = deferred();
        ResumeService[service].mockReturnValueOnce(pending.promise);
        if (action === "save") act(() => { result.current.changeDraft({ title: "Pending save" }); });
        let operation;
        await act(async () => { operation = result.current[action](...args); });
        act(() => { result.current.startNew(); });
        await act(async () => { pending.reject(new Error("Previous document error")); await operation; });

        expect(result.current.draft).toMatchObject({ id: null, revision: null, title: "resume.defaultDraftTitle" });
        expect(result.current).toMatchObject({ dirty: false, busy: "", error: null, autosaveState: "idle" });
        expect(showToast).not.toHaveBeenCalled();
    });

    it("preserves newer title edits while adopting generated canvas output", async () => {
        const { result } = await openStudio();
        const pending = deferred();
        ResumeService.generate.mockReturnValueOnce(pending.promise);
        let generating;
        act(() => { generating = result.current.generateFromProfile(); });
        act(() => { result.current.changeDraft({ title: "Typed during generation" }); });
        const generated = resumeDraft({ id: OTHER_ID, canvas_document: { generated: true } });
        await act(async () => { pending.resolve(generated); await generating; });

        expect(result.current.draft).toMatchObject({ id: OTHER_ID, title: "Typed during generation", canvas_document: { generated: true } });
        expect(result.current.dirty).toBe(true);
    });

    it("keeps edits made during deletion as an unsaved draft instead of modifying the successor", async () => {
        const { result } = await openStudio();
        const pending = deferred();
        ResumeService.remove.mockReturnValueOnce(pending.promise);
        ResumeService.list.mockResolvedValueOnce([otherDraft()]);
        let removing;
        act(() => { removing = result.current.remove(); });
        act(() => { result.current.changeDraft({ title: "Keep this newer work" }); });
        await act(async () => { pending.resolve(); await removing; });

        expect(result.current.draft).toMatchObject({ id: null, revision: null, title: "Keep this newer work", versions: [] });
        expect(result.current).toMatchObject({ dirty: true, autosaveState: "pending" });
    });

    it("retains save ownership when competing photo or promotion actions are invoked", async () => {
        const { result } = await openStudio();
        const pending = deferred();
        ResumeService.update.mockReturnValueOnce(pending.promise);
        act(() => { result.current.changeDraft({ title: "Pending autosave" }); });
        await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
        await act(async () => {
            await result.current.uploadPhoto(new File(["image"], "photo.png"));
            await result.current.promoteClaim("claim");
        });
        expect(CareerService.uploadPhoto).not.toHaveBeenCalled();
        expect(ResumeService.promoteClaim).not.toHaveBeenCalled();
        expect(result.current.busy).toBe("autosave");
        await act(async () => { pending.resolve(resumeDraft({ revision: 2 })); });
        expect(result.current.draft.revision).toBe(2);
        ResumeService.promoteClaim.mockResolvedValueOnce(resumeDraft({ revision: 3 }));
        await act(async () => { await result.current.promoteClaim("claim"); });
        expect(ResumeService.promoteClaim).toHaveBeenCalledWith(RESUME_ID,
            expect.objectContaining({ expected_revision: 2 }), REQUEST_OPTIONS);
    });

    it("does not let an older autosave failure clear the next load status", async () => {
        const { result } = await openStudio();
        const saving = deferred();
        const loading = deferred();
        ResumeService.update.mockReturnValueOnce(saving.promise);
        act(() => { result.current.changeDraft({ title: "Pending autosave" }); });
        await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
        ResumeService.get.mockReturnValueOnce(loading.promise);
        let selecting;
        act(() => { selecting = result.current.loadDraft(OTHER_ID); });
        await act(async () => { saving.reject(new Error("Old autosave failed")); });
        expect(result.current.busy).toBe("load");
        expect(result.current.error).toBeNull();
        await act(async () => { loading.resolve(otherDraft()); await selecting; });
        expect(result.current).toMatchObject({ busy: "", error: null, autosaveState: "idle" });
    });

    it("keeps initialization loading until the latest retry completes", async () => {
        const { result } = await openStudio();
        const first = deferred();
        const second = deferred();
        CareerService.getProfile.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
        let firstLoad;
        let secondLoad;
        act(() => { firstLoad = result.current.initialize(); });
        act(() => { secondLoad = result.current.initialize(); });
        await act(async () => { first.resolve(careerProfile()); await firstLoad; });
        expect(result.current.loading).toBe(true);
        expect(result.current.busy).toBe("load");
        await act(async () => { second.resolve(careerProfile()); await secondLoad; });
        expect(result.current).toMatchObject({ loading: false, busy: "", error: null });
    });

    it("preserves only actual newer edits across save and publication responses", async () => {
        const { result } = await openStudio();
        const saving = deferred();
        const publishing = deferred();
        ResumeService.update.mockReturnValueOnce(saving.promise);
        ResumeService.publish.mockReturnValueOnce(publishing.promise);
        act(() => { result.current.changeDraft({ title: "Snapshot" }); });
        let publication;
        act(() => { publication = result.current.publish(); });
        act(() => { result.current.changeDraft({ title: "Newer title" }); });
        await act(async () => { saving.resolve(resumeDraft({ title: "Snapshot", revision: 2 })); });
        ResumeService.get.mockResolvedValueOnce(resumeDraft({
            title: "Snapshot", revision: 3, canvas_document: { published: true },
        }));
        await act(async () => { publishing.resolve(); await publication; });
        expect(result.current.draft).toMatchObject({
            title: "Newer title", revision: 3, canvas_document: { published: true },
        });
        expect(result.current.dirty).toBe(true);
    });

    it("initializes successfully through StrictMode effect cleanup and replay", async () => {
        let view;
        await act(async () => {
            view = renderHook(() => useResumeStudio(), { wrapper: StrictMode });
        });
        expect(view.result.current).toMatchObject({ loading: false, busy: "", error: null });
        expect(view.result.current.draft.id).toBe(RESUME_ID);
        expect(CareerService.getProfile).toHaveBeenCalledTimes(2);
    });

    it("does not continue publication or show a toast after unmounting during save", async () => {
        const view = await openStudio();
        const pending = deferred();
        ResumeService.update.mockReturnValueOnce(pending.promise);
        act(() => { view.result.current.changeDraft({ title: "Pending publish" }); });
        let publishing;
        act(() => { publishing = view.result.current.publish(); });
        view.unmount();
        await act(async () => { pending.resolve(resumeDraft({ revision: 2 })); await publishing; });
        expect(ResumeService.publish).not.toHaveBeenCalled();
        expect(showToast).not.toHaveBeenCalled();
    });
});
