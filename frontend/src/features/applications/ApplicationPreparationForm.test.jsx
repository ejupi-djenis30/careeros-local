import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { application } from "../../test/fixtures";
import { renderWithItalian as render } from "../../test/renderWithI18n";
import { ApplicationPreparationForm } from "./ApplicationPreparationForm";

const updatePreparation = vi.fn();

vi.mock("../../services/applications", () => ({
    ApplicationService: {
        updatePreparation: (...args) => updatePreparation(...args),
    },
}));

describe("ApplicationPreparationForm", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        updatePreparation.mockResolvedValue(application({ revision: 2 }));
    });

    it("updates the resolvable preflight fields with the current revision", async () => {
        const user = userEvent.setup();
        const onUpdated = vi.fn();
        const onClose = vi.fn();
        render(
            <MemoryRouter>
                <ApplicationPreparationForm
                    application={application()}
                    resumeVersions={[{ id: "resume-version-1", label: "ATS · v1.0.0" }]}
                    onUpdated={onUpdated}
                    onClose={onClose}
                />
            </MemoryRouter>,
        );

        expect(screen.getByRole("button", { name: "Salva e ricontrolla" })).toBeDisabled();
        expect(screen.getByRole("heading", { name: "Modifica pacchetto candidatura" })).toHaveFocus();
        await user.clear(screen.getByLabelText("Ruolo"));
        await user.type(screen.getByLabelText("Ruolo"), "Senior Platform Engineer");
        await user.clear(screen.getByLabelText("Azienda"));
        await user.type(screen.getByLabelText("Azienda"), "Local Systems AG");
        await user.type(screen.getByLabelText("Descrizione del ruolo"), "A detailed local role description");
        await user.type(screen.getByLabelText("URL di candidatura"), "https://example.test/apply");
        await user.type(screen.getByLabelText("Email di candidatura"), "jobs@example.test");
        await user.selectOptions(screen.getByLabelText("Versione CV pubblicata"), "resume-version-1");
        await user.click(screen.getByRole("button", { name: "Salva e ricontrolla" }));

        await waitFor(() => expect(updatePreparation).toHaveBeenCalledWith(
            "44444444-4444-4444-8444-444444444444",
            {
                expected_revision: 1,
                title: "Senior Platform Engineer",
                company: "Local Systems AG",
                description: "A detailed local role description",
                application_url: "https://example.test/apply",
                application_email: "jobs@example.test",
                resume_version_id: "resume-version-1",
            },
        ));
        expect(onUpdated).toHaveBeenCalledWith(expect.objectContaining({ revision: 2 }));
        expect(onClose).toHaveBeenCalledOnce();
    });
});
