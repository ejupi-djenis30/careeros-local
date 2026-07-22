import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithItalian as render } from "../../test/renderWithI18n";
import { ApplicationReadiness } from "./ApplicationReadiness";

const readiness = vi.fn();
const downloadReadiness = vi.fn();
const saveBlob = vi.fn();

vi.mock("../../services/applications", () => ({
    ApplicationService: {
        readiness: (...args) => readiness(...args),
        downloadReadiness: (...args) => downloadReadiness(...args),
    },
}));
vi.mock("../../lib/download", () => ({ saveBlob: (...args) => saveBlob(...args) }));

const REPORT = {
    status: "blocked",
    completeness_score: 72,
    blocker_count: 1,
    warning_count: 1,
    fingerprint: "a".repeat(64),
    checks: [
        {
            id: "role_identity",
            status: "pass",
            points_awarded: 10,
            points_available: 10,
            evidence: [
                { key: "title_present", value: "True" },
                { key: "company_present", value: "True" },
            ],
            action: null,
        },
        {
            id: "role_description",
            status: "blocker",
            points_awarded: 0,
            points_available: 14,
            evidence: [
                { key: "description_characters", value: "34" },
                { key: "minimum_characters", value: "120" },
            ],
            action: "capture_role_description",
        },
    ],
};

describe("ApplicationReadiness", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        readiness.mockResolvedValue(REPORT);
        downloadReadiness.mockResolvedValue({
            blob: new Blob(["report"]),
            filename: "careeros-application-app-1-readiness.json",
        });
    });

    it("explains the completeness score with evidence and corrective actions", async () => {
        const onEditPreparation = vi.fn();
        const user = userEvent.setup();
        render(<MemoryRouter><ApplicationReadiness applicationId="app-1" applicationRevision={4} onEditPreparation={onEditPreparation} /></MemoryRouter>);

        expect(await screen.findByRole("heading", { name: "Preparazione candidatura" })).toBeInTheDocument();
        expect(screen.getByText(/non è una probabilità di assunzione/i)).toBeInTheDocument();
        const score = screen.getByRole("progressbar", { name: "Completezza del pacchetto candidatura" });
        expect(score).toHaveAttribute("aria-valuenow", "72");
        expect(screen.getByText("Identità del ruolo")).toBeInTheDocument();
        expect(screen.getByText("Descrizione del ruolo")).toBeInTheDocument();
        expect(screen.getByText("Salva una descrizione del ruolo sufficiente per preparare la candidatura.")).toBeInTheDocument();
        expect(screen.getByText("Nessuna azione necessaria.")).toBeInTheDocument();
        expect(screen.getAllByText("Sì")).toHaveLength(2);
        expect(screen.getByRole("link", { name: /Apri Career Vault/i })).toHaveAttribute("href", "/profile");
        expect(screen.getByRole("link", { name: /Apri Resume Studio/i })).toHaveAttribute("href", "/resumes");
        await user.click(screen.getByRole("button", { name: /Modifica pacchetto/i }));
        expect(onEditPreparation).toHaveBeenCalledOnce();
    });

    it("downloads the canonical report returned by the authenticated local API", async () => {
        const user = userEvent.setup();
        render(<MemoryRouter><ApplicationReadiness applicationId="app-1" applicationRevision={4} /></MemoryRouter>);
        await screen.findByRole("progressbar");

        await user.click(screen.getByRole("button", { name: /JSON/i }));

        await waitFor(() => expect(downloadReadiness).toHaveBeenCalledWith("app-1", "json"));
        expect(saveBlob).toHaveBeenCalledWith(expect.objectContaining({
            filename: "careeros-application-app-1-readiness.json",
        }));
    });
});
