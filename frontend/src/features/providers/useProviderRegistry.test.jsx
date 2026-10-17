import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProviderService } from "../../services/providers";
import { emptyProvider, PRESERVE_SECRET, REDACTED_SECRET } from "./providerModel";
import { useProviderRegistry } from "./useProviderRegistry";

vi.mock("../../services/providers", () => ({
    ProviderService: {
        list: vi.fn(), validate: vi.fn(), create: vi.fn(), update: vi.fn(),
        remove: vi.fn(), setState: vi.fn(), importDocument: vi.fn(), importPack: vi.fn(),
    },
}));

const t = (key, variables) => key === "providers.imported" ? `${key}:${variables.count}` : key;
const provider = (changes = {}) => ({
    ...emptyProvider(), id: "provider-one", revision: 4,
    key: "example_jobs", display_name: "Example Jobs",
    request: {
        ...emptyProvider().request, base_url: "https://jobs.example.test",
        headers: { Authorization: REDACTED_SECRET },
    },
    ...changes,
});
const otherProvider = () => provider({ id: "provider-two", key: "other_jobs" });
const catalog = (installed = [provider(), otherProvider()]) => ({
    installed, available_packs: [{ id: "reviewed-pack", version: "1.0.0" }],
});

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return { promise, resolve, reject };
}

async function openRegistry() {
    const view = renderHook(() => useProviderRegistry(t));
    await waitFor(() => expect(view.result.current.loading).toBe(false));
    return view;
}

describe("provider write acknowledgements", () => {
    beforeEach(() => {
        vi.resetAllMocks();
        vi.spyOn(window, "confirm").mockReturnValue(true);
        ProviderService.list.mockResolvedValue(catalog());
        ProviderService.validate.mockResolvedValue({ valid: true });
    });
    afterEach(() => { vi.restoreAllMocks(); });

    it("adopts a created provider and redacted headers when the subsequent catalog read fails", async () => {
        ProviderService.list.mockResolvedValueOnce(catalog([otherProvider()]));
        const { result } = await openRegistry();
        act(() => {
            result.current.edit({ ...provider(), id: undefined, revision: undefined });
            result.current.setAdvanced((current) => ({
                ...current, headers: JSON.stringify({ Authorization: "synthetic-local-header" }),
            }));
        });
        ProviderService.create.mockResolvedValue(provider({ revision: 1 }));
        ProviderService.list.mockRejectedValueOnce(new Error("catalog unavailable"));

        await act(async () => { await result.current.save({ preventDefault() {} }); });

        expect(result.current.provider).toMatchObject({ id: "provider-one", revision: 1 });
        expect(JSON.parse(result.current.advanced.headers)).toEqual({ Authorization: REDACTED_SECRET });
        expect(result.current.catalog.installed).toEqual([otherProvider(), provider({ revision: 1 })]);
        expect(result.current.catalog.available_packs).toEqual(catalog().available_packs);
        expect(result.current.message).toContain("providers.saved");
        expect(result.current.message).toContain("providers.refreshError");
        expect(result.current.busy).toBe(false);

        ProviderService.update.mockResolvedValue(provider({ revision: 2 }));
        ProviderService.list.mockRejectedValueOnce(new Error("catalog still unavailable"));
        await act(async () => { await result.current.save({ preventDefault() {} }); });
        expect(ProviderService.create).toHaveBeenCalledTimes(1);
        expect(ProviderService.update).toHaveBeenCalledWith("provider-one", expect.objectContaining({
            expected_revision: 1,
            request: expect.objectContaining({ headers: { Authorization: PRESERVE_SECRET } }),
        }), expect.any(AbortSignal));
    });

    it("retains the acknowledged update revision through a read failure and uses it for the next save", async () => {
        const { result } = await openRegistry();
        act(() => {
            result.current.edit(provider());
            result.current.setAdvanced((current) => ({
                ...current, headers: JSON.stringify({ Authorization: "synthetic-local-header" }),
            }));
        });
        ProviderService.update.mockResolvedValueOnce(provider({ revision: 5 }));
        ProviderService.list.mockRejectedValueOnce(new Error("catalog unavailable"));

        await act(async () => { await result.current.save({ preventDefault() {} }); });

        expect(result.current.provider.revision).toBe(5);
        expect(JSON.parse(result.current.advanced.headers)).toEqual({ Authorization: REDACTED_SECRET });
        expect(result.current.catalog.installed[0].revision).toBe(5);
        ProviderService.update.mockResolvedValueOnce(provider({ revision: 6 }));
        await act(async () => { await result.current.save({ preventDefault() {} }); });
        expect(ProviderService.update.mock.calls[1][1].expected_revision).toBe(5);
    });

    it("removes an acknowledged deletion from the catalog and selected editor despite a read failure", async () => {
        const { result } = await openRegistry();
        act(() => { result.current.edit(provider()); });
        ProviderService.remove.mockResolvedValue(null);
        ProviderService.list.mockRejectedValueOnce(new Error("catalog unavailable"));

        await act(async () => { await result.current.remove(provider()); });

        expect(result.current.catalog.installed).toEqual([otherProvider()]);
        expect(result.current.provider.id).toBeUndefined();
        expect(JSON.parse(result.current.advanced.headers)).toEqual({});
        expect(result.current.message).toContain("providers.deleted");
        expect(result.current.message).toContain("providers.refreshError");
        expect(result.current.busy).toBe(false);
    });

    it("adopts a toggle revision while preserving unsaved editor fields and uses the confirmed state next", async () => {
        const { result } = await openRegistry();
        act(() => {
            result.current.edit(provider({ display_name: "Unsaved local name" }));
            result.current.setAdvanced((current) => ({ ...current, queryParams: '{"q":"local draft"}' }));
        });
        ProviderService.setState.mockResolvedValueOnce(provider({ enabled: true, revision: 5 }));
        ProviderService.list.mockRejectedValueOnce(new Error("catalog unavailable"));

        await act(async () => { await result.current.toggle(provider()); });

        expect(result.current.catalog.installed[0]).toMatchObject({ enabled: true, revision: 5 });
        expect(result.current.provider).toMatchObject({ enabled: true, revision: 5, display_name: "Unsaved local name" });
        expect(result.current.advanced.queryParams).toBe('{"q":"local draft"}');
        expect(result.current.message).toContain("providers.enabledMessage");
        expect(result.current.message).toContain("providers.refreshError");
        ProviderService.setState.mockResolvedValueOnce(provider({ enabled: false, revision: 6 }));
        await act(async () => { await result.current.toggle(result.current.catalog.installed[0]); });
        expect(ProviderService.setState.mock.calls[1].slice(0, 3)).toEqual(["provider-one", 5, false]);
    });

    it.each(["importDocument", "importPack"])("retains the %s acknowledgement and count when catalog reconciliation fails", async (method) => {
        const { result } = await openRegistry();
        act(() => { result.current.edit(provider({ display_name: "Unsaved local edit" })); });
        const configuration = {
            ...emptyProvider(), key: "imported_jobs", display_name: "Imported Jobs",
            request: { ...emptyProvider().request, base_url: "https://jobs.example.test" },
        };
        const imported = [{ ...configuration, id: "imported-provider", revision: 1 }];
        if (method === "importPack") imported.push({ ...otherProvider(), revision: 9 });
        ProviderService[method].mockResolvedValue({
            source_id: method === "importPack" ? "reviewed-pack" : null, activated: false, imported,
        });
        ProviderService.list.mockRejectedValueOnce(new Error("catalog unavailable"));
        const input = method === "importDocument"
            ? { kind: "provider", format_version: 1, provider: { kind: "declarative", configuration } }
            : "reviewed-pack";

        await act(async () => { await result.current[method](input, false); });

        expect(ProviderService[method]).toHaveBeenCalledWith(input, false, expect.any(AbortSignal));
        expect(result.current.message).toContain(`providers.imported:${method === "importDocument" ? 1 : 2}`);
        expect(result.current.message).toContain("providers.refreshError");
        expect(result.current.message).not.toContain("providers.importError");
        expect(result.current.catalog.installed).toContainEqual(imported[0]);
        if (method === "importPack") expect(result.current.catalog.installed).toContainEqual(imported[1]);
        expect(result.current.catalog.installed.find((item) => item.id === "provider-one")).toEqual(provider());
        expect(result.current.catalog.available_packs).toEqual(catalog().available_packs);
        expect(result.current.provider.display_name).toBe("Unsaved local edit");
        expect(result.current.busy).toBe(false);
        expect(ProviderService[method]).toHaveBeenCalledTimes(1);
    });

    it("does not replace newer editor changes when the acknowledgement's pending refresh fails", async () => {
        const { result } = await openRegistry();
        act(() => { result.current.edit(provider()); });
        const refresh = deferred();
        ProviderService.update.mockResolvedValue(provider({ revision: 5 }));
        ProviderService.list.mockReturnValueOnce(refresh.promise);
        let saving;
        act(() => { saving = result.current.save({ preventDefault() {} }); });
        await waitFor(() => expect(result.current.provider.revision).toBe(5));
        act(() => {
            result.current.setProvider((current) => ({ ...current, display_name: "Newer local edit" }));
        });
        await act(async () => { refresh.reject(new Error("catalog unavailable")); await saving; });
        expect(result.current.provider).toMatchObject({ revision: 5, display_name: "Newer local edit" });
    });

    it("does not apply a late catalog response after unmounting during reconciliation", async () => {
        const view = await openRegistry();
        act(() => { view.result.current.edit(provider()); });
        const refresh = deferred();
        ProviderService.update.mockResolvedValue(provider({ revision: 5 }));
        ProviderService.list.mockReturnValueOnce(refresh.promise);
        let saving;
        act(() => { saving = view.result.current.save({ preventDefault() {} }); });
        await waitFor(() => expect(view.result.current.provider.revision).toBe(5));
        const signal = ProviderService.list.mock.calls[1][0];
        view.unmount();
        await act(async () => { refresh.resolve(catalog()); await saving; });
        expect(signal.aborted).toBe(true);
        expect(view.result.current.catalog.installed[0].revision).toBe(5);
        expect(view.result.current.message).toBe("");
    });

    it("retains a different selected draft when a provider deletion is acknowledged", async () => {
        const { result } = await openRegistry();
        act(() => { result.current.edit({ ...otherProvider(), display_name: "Local draft" }); });
        ProviderService.remove.mockResolvedValue(null);
        ProviderService.list.mockRejectedValueOnce(new Error("catalog unavailable"));
        await act(async () => { await result.current.remove(provider()); });
        expect(result.current.provider).toMatchObject({ id: "provider-two", display_name: "Local draft" });
        expect(result.current.catalog.installed).toEqual([otherProvider()]);
    });

    it("retains the original editor and catalog on an actual write rejection", async () => {
        const { result } = await openRegistry();
        act(() => { result.current.edit(provider({ display_name: "Unsaved local name" })); });
        ProviderService.update.mockRejectedValue(new Error("revision conflict"));
        await act(async () => { await result.current.save({ preventDefault() {} }); });
        expect(result.current.provider).toMatchObject({ revision: 4, display_name: "Unsaved local name" });
        expect(result.current.catalog).toEqual(catalog());
        expect(result.current.message).toBe("revision conflict");
        expect(ProviderService.list).toHaveBeenCalledTimes(1);
        expect(result.current.busy).toBe(false);
    });

    it("does not acknowledge a delayed write or refresh after unmount and keeps writes single-flight", async () => {
        const view = await openRegistry();
        act(() => { view.result.current.edit(provider()); });
        const write = deferred();
        ProviderService.update.mockReturnValueOnce(write.promise);
        let saving;
        act(() => { saving = view.result.current.save({ preventDefault() {} }); });
        await waitFor(() => expect(ProviderService.update).toHaveBeenCalledTimes(1));
        await act(async () => { await view.result.current.save({ preventDefault() {} }); });
        expect(ProviderService.update).toHaveBeenCalledTimes(1);
        const signal = ProviderService.update.mock.calls[0][2];
        view.unmount();
        await act(async () => { write.resolve(provider({ revision: 5 })); await saving; });
        expect(signal.aborted).toBe(true);
        expect(ProviderService.list).toHaveBeenCalledTimes(1);
        expect(view.result.current.provider.revision).toBe(4);
    });
});
