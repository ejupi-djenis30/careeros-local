import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithItalian as render } from "../../test/renderWithI18n";
import { LocalModelStatus } from "./LocalModelStatus";

const refresh = vi.fn();
const hook = vi.fn();
vi.mock("./useLocalModelStatus", () => ({ useLocalModelStatus: () => hook() }));

describe("LocalModelStatus", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        hook.mockReturnValue({ status: { loading: false, available: true, ready: true, configured_model: "qwen3:1.7b", installed_models: ["qwen3:1.7b"] }, refresh });
    });

    it("identifies the configured local model and can refresh it", async () => {
        const user = userEvent.setup();
        render(<LocalModelStatus />);
        expect(screen.getByText("motore locale · qwen3:1.7b")).toBeInTheDocument();
        expect(screen.getByText(/solo su questo dispositivo/)).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: "Ricontrolla modello locale" }));
        expect(refresh).toHaveBeenCalledTimes(1);
    });

    it("presents an unavailable runtime as required analysis setup", () => {
        hook.mockReturnValue({ status: { loading: false, available: false, ready: false, configured_model: "qwen3:1.7b", installed_models: [], error_code: "local_runtime_unreachable" }, refresh });
        render(<LocalModelStatus />);
        expect(screen.getByText("Configurazione dell’analisi locale necessaria")).toBeInTheDocument();
        expect(screen.getByText(/Archivio, CV, candidature ed esportazioni restano disponibili/)).toBeInTheDocument();
    });
});
