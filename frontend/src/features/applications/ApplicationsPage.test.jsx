import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { application } from "../../test/fixtures";
import { ApplicationsPage } from "./ApplicationsPage";

const list = vi.fn();
const create = vi.fn();
const showToast = vi.fn();

vi.mock("../../services/applications", () => ({ ApplicationService: { list: (...args) => list(...args), create: (...args) => create(...args), get: vi.fn(), addEvent: vi.fn() } }));
vi.mock("../../services/resumes", () => ({ ResumeService: { list: vi.fn(async () => []), get: vi.fn() } }));
vi.mock("../../context/ToastContext", () => ({ useToast: () => ({ showToast }) }));

describe("ApplicationsPage", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        list.mockResolvedValue([]);
        create.mockResolvedValue(application());
    });

    it("creates a local job snapshot from a deep-linked job id", async () => {
        const user = userEvent.setup();
        render(<MemoryRouter initialEntries={["/applications?jobId=42"]}><ApplicationsPage /></MemoryRouter>);
        const submit = await screen.findByRole("button", { name: "Crea candidatura" });
        await user.type(screen.getByLabelText("Nota iniziale"), "Contattata tramite referral");
        await user.click(submit);

        await waitFor(() => expect(create).toHaveBeenCalledWith({ job_id: 42, initial_stage: "saved", resume_version_id: null, note: "Contattata tramite referral" }));
        expect(await screen.findByText("Snapshot locale")).toBeInTheDocument();
        expect(showToast).toHaveBeenCalledWith(expect.stringContaining("pipeline"), "success");
    });

    it("creates a manual snapshot when no discovered job id exists", async () => {
        const user = userEvent.setup();
        render(<MemoryRouter initialEntries={["/applications"]}><ApplicationsPage /></MemoryRouter>);
        await user.click(await screen.findByRole("button", { name: "Aggiungi la prima candidatura" }));
        await user.type(screen.getByLabelText("Titolo"), "Security Engineer");
        await user.type(screen.getByLabelText("Azienda"), "Local Systems");
        await user.type(screen.getByLabelText("Località"), "Zurich");
        await user.click(screen.getByRole("button", { name: "Crea candidatura" }));

        await waitFor(() => expect(create).toHaveBeenCalledWith({
            manual_job: {
                title: "Security Engineer", company: "Local Systems", location: "Zurich",
                external_url: null, description: null,
            },
            initial_stage: "saved", resume_version_id: null, note: null,
        }));
    });
});
