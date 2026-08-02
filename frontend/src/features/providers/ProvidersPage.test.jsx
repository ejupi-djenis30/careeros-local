import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProviderService } from "../../services/providers";
import { assertAccessible } from "../../test/accessibility";
import { renderWithI18n } from "../../test/renderWithI18n";
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

describe("ProvidersPage", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        ProviderService.list.mockResolvedValue(catalog);
        ProviderService.validate.mockResolvedValue({ valid: true, warnings: [] });
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
        ProviderService.importPack.mockResolvedValue({ imported: [{ id: "provider-1" }] });
        renderWithI18n(<ProvidersPage />);

        await user.click(await screen.findByRole("button", { name: "Import pack" }));

        await waitFor(() => expect(ProviderService.importPack).toHaveBeenCalledWith(
            "careeros.switzerland.core",
            false,
        ));
        expect(await screen.findByText("Imported 1 provider(s).")).toBeInTheDocument();
    });
});
