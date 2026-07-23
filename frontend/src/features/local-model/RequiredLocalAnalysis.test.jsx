import { MemoryRouter } from "react-router-dom";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithI18n } from "../../test/renderWithI18n";
import { LocalModelService } from "../../services/localModel";
import { RequiredLocalAnalysis } from "./RequiredLocalAnalysis";

const refresh = vi.fn();
const statusHook = vi.fn();

vi.mock("./useLocalModelStatus", () => ({
    useLocalModelStatus: () => statusHook(),
}));
vi.mock("./ModelManager", () => ({
    ModelManager: () => <div data-testid="model-manager">model setup</div>,
}));
vi.mock("../../services/localModel", () => ({
    LocalModelService: { readiness: vi.fn() },
}));

function renderGate() {
    return renderWithI18n(
        <MemoryRouter>
            <RequiredLocalAnalysis><div>protected analysis</div></RequiredLocalAnalysis>
        </MemoryRouter>,
    );
}

function deferred() {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
}

describe("RequiredLocalAnalysis", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        statusHook.mockReturnValue({
            status: {
                loading: false,
                ready: false,
                runtime: "llama.cpp",
                configured_model: "qwen3-1.7b-q8",
            },
            refresh,
        });
    });

    it("keeps analysis locked and presents local setup when no model is ready", () => {
        renderGate();

        expect(screen.queryByText("protected analysis")).not.toBeInTheDocument();
        expect(screen.getByRole("heading", { name: /Prepare the on-device model/ })).toBeInTheDocument();
        expect(screen.getByTestId("model-manager")).toBeInTheDocument();
        expect(LocalModelService.readiness).not.toHaveBeenCalled();
    });

    it("unlocks analysis only after the structured readiness probe passes", async () => {
        statusHook.mockReturnValue({
            status: {
                loading: false,
                ready: true,
                runtime: "llama.cpp",
                configured_model: "qwen3-1.7b-q8",
            },
            refresh,
        });
        LocalModelService.readiness.mockResolvedValue({
            ready: true,
            model_id: "llama.cpp/qwen3-1.7b-q8",
            checks: [
                { code: "structured_output", status: "passed" },
            ],
        });

        renderGate();

        await waitFor(() => expect(screen.getByText("protected analysis")).toBeInTheDocument());
        expect(LocalModelService.readiness).toHaveBeenCalledTimes(1);
    });

    it("shows stable diagnostics and retries a failed schema probe", async () => {
        const user = userEvent.setup();
        statusHook.mockReturnValue({
            status: {
                loading: false,
                ready: true,
                runtime: "ollama",
                configured_model: "local-model",
            },
            refresh,
        });
        LocalModelService.readiness
            .mockResolvedValueOnce({
                ready: false,
                error_code: "structured_probe_failed",
                checks: [
                    { code: "endpoint_allowed", status: "passed" },
                    { code: "structured_output", status: "failed" },
                ],
            })
            .mockResolvedValueOnce({ ready: true, checks: [] });

        renderGate();

        expect(await screen.findByText(/response did not pass the required JSON contract/i)).toBeInTheDocument();
        expect(screen.queryByText("protected analysis")).not.toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Run readiness check again" }));
        await waitFor(() => expect(screen.getByText("protected analysis")).toBeInTheDocument());
        expect(LocalModelService.readiness).toHaveBeenCalledTimes(2);
    });

    it("aborts an in-flight readiness probe when navigation unmounts the gate", async () => {
        statusHook.mockReturnValue({
            status: {
                loading: false,
                ready: true,
                runtime: "llama.cpp",
                configured_model: "compact-local",
            },
            refresh,
        });
        LocalModelService.readiness.mockImplementation(() => new Promise(() => {}));

        const view = renderGate();
        await waitFor(() => expect(LocalModelService.readiness).toHaveBeenCalledTimes(1));
        const signal = LocalModelService.readiness.mock.calls[0][0].signal;
        expect(signal.aborted).toBe(false);

        view.unmount();
        expect(signal.aborted).toBe(true);
    });

    it("discards a readiness pass when the configured model identity changes", async () => {
        const firstProbe = deferred();
        const secondProbe = deferred();
        statusHook.mockReturnValue({
            status: { loading: false, ready: true, runtime: "ollama", configured_model: "model-a" },
            refresh,
        });
        LocalModelService.readiness
            .mockImplementationOnce(() => firstProbe.promise)
            .mockImplementationOnce(() => secondProbe.promise);

        const view = renderGate();
        await waitFor(() => expect(LocalModelService.readiness).toHaveBeenCalledTimes(1));

        statusHook.mockReturnValue({
            status: { loading: false, ready: true, runtime: "ollama", configured_model: "model-b" },
            refresh,
        });
        view.rerender(
            <MemoryRouter>
                <RequiredLocalAnalysis><div>protected analysis</div></RequiredLocalAnalysis>
            </MemoryRouter>,
        );
        await waitFor(() => expect(LocalModelService.readiness).toHaveBeenCalledTimes(2));

        firstProbe.resolve({ ready: true, checks: [] });
        await Promise.resolve();
        expect(screen.queryByText("protected analysis")).not.toBeInTheDocument();

        secondProbe.resolve({ ready: true, checks: [] });
        expect(await screen.findByText("protected analysis")).toBeInTheDocument();
    });

    it("announces the unlocked workflow and transfers focus after readiness", async () => {
        statusHook.mockReturnValue({
            status: { loading: false, ready: true, runtime: "ollama", configured_model: "model-a" },
            refresh,
        });
        LocalModelService.readiness.mockResolvedValue({ ready: true, checks: [] });

        renderGate();

        const unlocked = await screen.findByLabelText("Local analysis ready. Workflow unlocked.");
        await waitFor(() => expect(unlocked).toHaveFocus());
    });
});
