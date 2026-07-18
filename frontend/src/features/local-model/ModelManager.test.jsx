import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { assertAccessible } from "../../test/accessibility";
import { LocalModelService } from "../../services/localModel";
import { ModelManager } from "./ModelManager";

const refresh = vi.fn();
const hook = vi.fn();
vi.mock("./useLocalModelStatus", () => ({ useLocalModelStatus: () => hook() }));
vi.mock("../../services/localModel", () => ({
    LocalModelService: {
        catalog: vi.fn(),
        install: vi.fn(),
        replace: vi.fn(),
        cancel: vi.fn(),
        pause: vi.fn(),
        resume: vi.fn(),
        remove: vi.fn(),
        restart: vi.fn(),
    },
}));

const catalog = {
    models: [{
        key: "qwen3-1.7b-q8",
        displayName: "Qwen3 1.7B · Accurate compact",
        parameters: "1.7B",
        quantization: "Q8_0",
        sizeBytes: 1834426016,
        license: "Apache-2.0",
    }],
};

describe("ModelManager", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        LocalModelService.catalog.mockResolvedValue(catalog);
        LocalModelService.install.mockResolvedValue({ phase: "downloading_model" });
        LocalModelService.cancel.mockResolvedValue({ phase: "cancelled" });
        LocalModelService.pause.mockResolvedValue({ phase: "paused" });
        LocalModelService.resume.mockResolvedValue({ phase: "downloading_model" });
        LocalModelService.remove.mockResolvedValue({ status: { phase: "idle" } });
        hook.mockReturnValue({
            status: { loading: false, ready: false, available: false, managed: { phase: "idle" } },
            refresh,
        });
    });

    it("requires explicit license consent before installation", async () => {
        const user = userEvent.setup();
        render(<ModelManager />);

        const install = await screen.findByRole("button", { name: "Installa modello locale" });
        expect(install).toBeDisabled();
        await user.click(screen.getByRole("checkbox", { name: /Accetto la licenza Apache-2.0/ }));
        await user.click(install);

        await waitFor(() => expect(LocalModelService.install).toHaveBeenCalledWith("qwen3-1.7b-q8"));
        expect(refresh).toHaveBeenCalled();
    });

    it("shows verified progress and supports pause and destructive cancellation", async () => {
        const user = userEvent.setup();
        hook.mockReturnValue({
            status: {
                loading: false,
                ready: false,
                available: true,
                managed: { phase: "downloading_model", bytes_downloaded: 50, bytes_total: 100 },
            },
            refresh,
        });
        render(<ModelManager />);

        expect(await screen.findByRole("progressbar")).toHaveAttribute("value", "50");
        await user.click(screen.getByRole("button", { name: "Metti in pausa" }));
        expect(LocalModelService.pause).toHaveBeenCalledTimes(1);
        await user.click(screen.getByRole("button", { name: "Annulla e rimuovi download" }));
        expect(LocalModelService.cancel).toHaveBeenCalledTimes(1);
    });

    it("resumes a paused partial download without requiring new consent", async () => {
        const user = userEvent.setup();
        hook.mockReturnValue({
            status: {
                loading: false,
                ready: false,
                available: true,
                managed: { phase: "paused", bytes_downloaded: 25, bytes_total: 100 },
            },
            refresh,
        });
        render(<ModelManager />);

        expect(await screen.findByText("Download in pausa")).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Riprendi download" }));
        expect(LocalModelService.resume).toHaveBeenCalledTimes(1);
    });

    it("can remove an installed local model", async () => {
        const user = userEvent.setup();
        hook.mockReturnValue({
            status: {
                loading: false,
                ready: true,
                available: true,
                managed: { phase: "ready", model_key: "qwen3-1.7b-q8", model_installed: true, runtime_installed: true },
            },
            refresh,
        });
        render(<ModelManager />);

        await user.click(await screen.findByRole("button", { name: "Rimuovi modello" }));
        expect(LocalModelService.remove).toHaveBeenCalledTimes(1);
    });

    it("passes the model setup accessibility and keyboard gate", async () => {
        const user = userEvent.setup();
        const { container } = render(<main><h1>Gestione modello locale</h1><ModelManager /></main>);
        const consent = await screen.findByRole("checkbox", { name: /Accetto la licenza Apache-2.0/ });

        await assertAccessible(container);
        await user.tab();
        expect(screen.getByRole("button", { name: "Ricontrolla modello locale" })).toHaveFocus();
        await user.tab();
        expect(consent).toHaveFocus();
        await user.keyboard(" ");
        await user.tab();
        const install = screen.getByRole("button", { name: "Installa modello locale" });
        expect(install).toHaveFocus();
        await user.keyboard("{Enter}");
        await waitFor(() => expect(LocalModelService.install).toHaveBeenCalledTimes(1));
    });
});
