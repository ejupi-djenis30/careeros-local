import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProviderService } from "../../services/providers";
import { assertAccessible } from "../../test/accessibility";
import { renderWithI18n } from "../../test/renderWithI18n";
import { createTranslator, I18nContext } from "../../i18n/runtime";
import { ProvidersPage } from "./ProvidersPage";
import { emptyProvider } from "./providerModel";

vi.mock("../../services/providers", () => ({
    ProviderService: {
        list: vi.fn(),
        validate: vi.fn(),
        create: vi.fn(),
        update: vi.fn(),
        importDocument: vi.fn(),
        importPack: vi.fn(),
        remove: vi.fn(),
        setState: vi.fn(),
        test: vi.fn(),
    },
}));

const catalog = {
    installed: [],
    available_packs: [{
        id: "careeros.switzerland.core",
        version: "1.0.0",
        name: "Swiss job providers",
        description: "Reviewed Swiss native, canton and specialist providers",
        provider_keys: [
            "job_room",
            "swissdevjobs",
            "adecco",
            "canton_bern",
            "canton_solothurn",
            "canton_lucerne",
            "fmh_doctor_jobs",
            "vmi_npo_jobs",
            "swissolar_jobs",
            "kampajobs",
            "jobs_for_change",
        ],
    }],
};

const installedProvider = () => ({
    ...emptyProvider(), id: "8f4cd5cc-86e3-4a8d-a122-f57b98eea9fd", revision: 4,
    key: "example_jobs", display_name: "Example Jobs",
    request: { ...emptyProvider().request, base_url: "https://jobs.example.com" },
});

async function fillProvider() {
    await screen.findByRole("heading", { name: "Bring your own job sources" });
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Example Jobs" } });
    fireEvent.change(screen.getByLabelText("Stable key"), { target: { value: "example_jobs" } });
    fireEvent.change(screen.getByLabelText("HTTPS origin"), { target: { value: "https://jobs.example.com" } });
}

describe("ProvidersPage", () => {
    beforeEach(() => {
        vi.resetAllMocks();
        ProviderService.list.mockResolvedValue(catalog);
        ProviderService.validate.mockResolvedValue({ valid: true, warnings: [] });
    });

    afterEach(() => { vi.restoreAllMocks(); });

    it("loads Italian feature copy while preserving the unsaved provider draft across language switches", async () => {
        const localized = (language) => <I18nContext.Provider value={{ language, t: createTranslator(language) }}><ProvidersPage /></I18nContext.Provider>;
        const view = renderWithI18n(localized("en"));
        await fillProvider();
        view.rerender(localized("it"));
        await screen.findByRole("heading", { name: "Aggiungi le tue sorgenti di lavoro" });
        expect(screen.getByLabelText("Nome visualizzato")).toHaveValue("Example Jobs");
        view.rerender(localized("en"));
        await screen.findByRole("heading", { name: "Bring your own job sources" });
        expect(screen.getByLabelText("Display name")).toHaveValue("Example Jobs");
        expect(ProviderService.list).toHaveBeenCalledTimes(1);
        expect(ProviderService.create).not.toHaveBeenCalled();
    });

    it("makes no acquisition or installation request when the registry opens", async () => {
        renderWithI18n(<ProvidersPage />);
        await screen.findByRole("heading", { name: "Bring your own job sources" });
        expect(ProviderService.test).not.toHaveBeenCalled();
        expect(ProviderService.create).not.toHaveBeenCalled();
        expect(ProviderService.importPack).not.toHaveBeenCalled();
        expect(screen.getByRole("checkbox", { name: /Enable imported providers immediately/ })).not.toBeChecked();
        expect(screen.getByRole("checkbox", { name: /^Enable network access/ })).not.toBeChecked();
    });

    it("fails closed when validation does not approve the configuration", async () => {
        ProviderService.validate.mockResolvedValue({ valid: false, warnings: [] });
        renderWithI18n(<ProvidersPage />);
        await fillProvider();
        fireEvent.submit(screen.getByRole("button", { name: "Save provider" }).closest("form"));
        expect(await screen.findByText("The provider configuration did not pass validation.")).toBeInTheDocument();
        expect(ProviderService.create).not.toHaveBeenCalled();
        expect(ProviderService.update).not.toHaveBeenCalled();
        expect(ProviderService.test).not.toHaveBeenCalled();
        expect(screen.getByLabelText("Display name")).toHaveValue("Example Jobs");
    });

    it("aborts validation on unmount and never continues into a write", async () => {
        let finish;
        const pending = new Promise((resolve) => { finish = resolve; });
        ProviderService.validate.mockReturnValue(pending);
        const view = renderWithI18n(<ProvidersPage />);
        await fillProvider();
        fireEvent.submit(screen.getByRole("button", { name: "Save provider" }).closest("form"));
        const signal = ProviderService.validate.mock.calls[0][1];
        expect(signal.aborted).toBe(false);
        view.unmount();
        await act(async () => { finish({ valid: true }); await pending; });
        expect(signal.aborted).toBe(true);
        expect(ProviderService.create).not.toHaveBeenCalled();
        expect(ProviderService.list).toHaveBeenCalledTimes(1);
    });

    it("keeps writes single-flight and disables editor inputs until completion", async () => {
        let finish;
        const pending = new Promise((resolve) => { finish = resolve; });
        ProviderService.validate.mockReturnValue(pending);
        ProviderService.create.mockResolvedValue(installedProvider());
        renderWithI18n(<ProvidersPage />);
        await fillProvider();
        const form = screen.getByRole("button", { name: "Save provider" }).closest("form");
        fireEvent.submit(form);
        fireEvent.submit(form);
        expect(ProviderService.validate).toHaveBeenCalledTimes(1);
        expect(screen.getByLabelText("Display name")).toBeDisabled();
        expect(screen.getByRole("button", { name: "New provider" })).toBeDisabled();
        await act(async () => { finish({ valid: true }); await pending; });
        await waitFor(() => expect(ProviderService.create).toHaveBeenCalledTimes(1));
        expect(ProviderService.create.mock.calls[0][0].enabled).toBe(false);
    });

    it("keeps editor, catalog and import controls disabled throughout the actual provider write", async () => {
        let finishWrite;
        const write = new Promise((resolve) => { finishWrite = resolve; });
        ProviderService.create.mockReturnValueOnce(write);
        ProviderService.list.mockResolvedValue({ ...catalog, installed: [installedProvider()] });
        renderWithI18n(<ProvidersPage />);
        await fillProvider();
        fireEvent.submit(screen.getByRole("button", { name: "Save provider" }).closest("form"));
        await waitFor(() => expect(ProviderService.create).toHaveBeenCalledTimes(1));

        const fields = screen.getByRole("button", { name: "Saving…" }).closest("fieldset");
        for (const control of fields.querySelectorAll("input, textarea, select, button")) {
            expect(control).toBeDisabled();
        }
        for (const name of ["New provider", "Edit", "Enable network access", "Test", "Delete", "Import pack"]) {
            expect(screen.getByRole("button", { name })).toBeDisabled();
        }
        expect(screen.getByLabelText(/^Provider or provider-pack JSON file/)).toBeDisabled();
        expect(screen.getByRole("checkbox", { name: /Enable imported providers immediately/ })).toBeDisabled();

        await act(async () => { finishWrite(installedProvider()); await write; });
        await waitFor(() => expect(screen.getByLabelText("Display name")).toBeEnabled());
    });

    it("requires one-time network consent before testing a disabled source", async () => {
        const consent = vi.spyOn(window, "confirm").mockReturnValue(false);
        ProviderService.list.mockResolvedValue({ ...catalog, installed: [installedProvider()] });
        ProviderService.test.mockResolvedValue({ returned_count: 1, sample: [{ id: "one", title: "<script>inert</script>", company: "Example", location: "Bern" }] });
        renderWithI18n(<ProvidersPage />);
        const test = await screen.findByRole("button", { name: "Test" });
        fireEvent.click(test);
        expect(consent).toHaveBeenCalledWith(expect.stringContaining("Example Jobs"));
        expect(consent).toHaveBeenCalledWith(expect.stringContaining("software engineer"));
        expect(ProviderService.test).not.toHaveBeenCalled();
        consent.mockReturnValue(true);
        fireEvent.click(test);
        await screen.findByRole("heading", { name: "Test sample: 1 jobs" });
        expect(ProviderService.test).toHaveBeenCalledWith(installedProvider().id,
            { query: "software engineer", location: "", language: "en", allow_network: true }, expect.any(AbortSignal));
        expect(ProviderService.setState).not.toHaveBeenCalled();
        expect(screen.getByText("<script>inert</script>")).toBeInTheDocument();
        expect(document.querySelector(".provider-test-result script")).toBeNull();
    });

    it("sends the installed revision when enabling and deleting a provider", async () => {
        vi.spyOn(window, "confirm").mockReturnValue(true);
        const provider = installedProvider();
        ProviderService.list.mockResolvedValue({ ...catalog, installed: [provider] });
        ProviderService.setState.mockResolvedValue({ ...provider, enabled: true, revision: 5 });
        renderWithI18n(<ProvidersPage />);
        fireEvent.click(await screen.findByRole("button", { name: "Enable network access" }));
        await screen.findByText("Provider enabled. It can participate in the next search.");
        expect(ProviderService.setState).toHaveBeenCalledWith(provider.id, 4, true, expect.any(AbortSignal));
        ProviderService.remove.mockResolvedValue(null);
        fireEvent.click(screen.getByRole("button", { name: "Delete" }));
        await waitFor(() => expect(ProviderService.remove).toHaveBeenCalledWith(provider.id, 4, expect.any(AbortSignal)));
    });

    it("requires explicit activation to import enabled providers", async () => {
        ProviderService.importPack.mockResolvedValue({ imported: [installedProvider()] });
        renderWithI18n(<ProvidersPage />);
        await screen.findByRole("button", { name: "Import pack" });
        fireEvent.click(screen.getByRole("checkbox", { name: /Enable imported providers immediately/ }));
        fireEvent.click(screen.getByRole("button", { name: "Import pack" }));
        await waitFor(() => expect(ProviderService.importPack).toHaveBeenCalledWith("careeros.switzerland.core", true, expect.any(AbortSignal)));
        expect(ProviderService.test).not.toHaveBeenCalled();
    });

    it("shows a retry instead of presenting a failed registry load as an empty vault", async () => {
        ProviderService.list.mockRejectedValueOnce(new Error("Unavailable"));
        renderWithI18n(<ProvidersPage />);
        const retry = await screen.findByRole("button", { name: "Retry loading providers" });
        expect(screen.queryByText(/No providers are installed/)).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Save provider" })).not.toBeInTheDocument();
        fireEvent.click(retry);
        await screen.findByRole("heading", { name: "Bring your own job sources" });
    });

    it("creates a declarative provider only after local validation", async () => {
        const user = userEvent.setup();
        const saved = {
            ...emptyProvider(),
            id: "8f4cd5cc-86e3-4a8d-a122-f57b98eea9fd",
            revision: 1,
            key: "example_jobs",
            display_name: "Example Jobs",
            request: {
                ...emptyProvider().request,
                base_url: "https://jobs.example.com",
            },
        };
        ProviderService.create.mockResolvedValue(saved);
        ProviderService.list
            .mockResolvedValueOnce(catalog)
            .mockResolvedValueOnce({ ...catalog, installed: [saved] });
        const { container } = renderWithI18n(<ProvidersPage />);
        await screen.findByRole("heading", { name: "Bring your own job sources" });

        await user.type(screen.getByLabelText("Display name"), "Example Jobs");
        await user.type(screen.getByLabelText("Stable key"), "example_jobs");
        const origin = screen.getByLabelText("HTTPS origin");
        await user.clear(origin);
        await user.type(origin, "https://jobs.example.com");
        await user.click(screen.getByRole("checkbox", { name: /Enable network access/ }));
        await user.click(screen.getByRole("button", { name: "Save provider" }));

        await waitFor(() => expect(ProviderService.create).toHaveBeenCalledTimes(1));
        expect(ProviderService.validate).toHaveBeenCalledTimes(1);
        expect(ProviderService.validate.mock.invocationCallOrder[0])
            .toBeLessThan(ProviderService.create.mock.invocationCallOrder[0]);
        const configuration = ProviderService.create.mock.calls[0][0];
        expect(configuration).toMatchObject({
            key: "example_jobs",
            enabled: true,
            adapter_kind: "json",
            request: { base_url: "https://jobs.example.com" },
            extraction: { items_path: "jobs" },
        });
        expect(configuration).not.toHaveProperty("expected_revision");
        expect(await screen.findByText(/Provider saved/)).toBeInTheDocument();
        await assertAccessible(container);
    });

    it("starts with no installed providers and offers the Swiss pack explicitly", async () => {
        const { container } = renderWithI18n(<ProvidersPage />);

        expect(await screen.findByText("Swiss job providers")).toBeInTheDocument();
        expect(screen.getByText("No providers are installed", { exact: false }))
            .toBeInTheDocument();
        expect(screen.queryByText("Job-Room")).not.toBeInTheDocument();
        expect(screen.getByText("Public HTTPS only", { exact: false })).toBeInTheDocument();
        await assertAccessible(container);
    });

    it("imports a pack disabled unless activation is explicitly selected", async () => {
        const user = userEvent.setup();
        ProviderService.importPack.mockResolvedValue({ imported: [installedProvider()] });
        renderWithI18n(<ProvidersPage />);

        await user.click(await screen.findByRole("button", { name: "Import pack" }));

        await waitFor(() => expect(ProviderService.importPack).toHaveBeenCalledWith(
            "careeros.switzerland.core",
            false,
            expect.any(AbortSignal),
        ));
        expect(await screen.findByText("Imported 1 provider(s).")).toBeInTheDocument();
    });
});
