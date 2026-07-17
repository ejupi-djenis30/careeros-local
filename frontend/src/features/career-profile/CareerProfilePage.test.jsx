import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { careerProfile, EXPERIENCE_ID } from "../../test/fixtures";
import { CareerProfilePage } from "./CareerProfilePage";

const getProfile = vi.fn();
const saveProfile = vi.fn();
const showToast = vi.fn();

vi.mock("../../services/career", () => ({ CareerService: { getProfile: (...args) => getProfile(...args), saveProfile: (...args) => saveProfile(...args), uploadSource: vi.fn() } }));
vi.mock("../../context/AuthContext", () => ({ useAuth: () => ({ user: "ada" }) }));
vi.mock("../../context/ToastContext", () => ({ useToast: () => ({ showToast }) }));

describe("CareerProfilePage", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        getProfile.mockResolvedValue(careerProfile());
        saveProfile.mockImplementation(async (payload) => careerProfile({ revision: payload.expected_revision + 1, headline: payload.headline }));
    });

    it("saves an explicit optimistic revision and the edited profile", async () => {
        const user = userEvent.setup();
        render(<CareerProfilePage />);
        const headline = await screen.findByLabelText("Titolo professionale");
        await user.clear(headline);
        await user.type(headline, "Principal engineer");
        await user.click(screen.getByRole("button", { name: "Salva Career Vault" }));

        await waitFor(() => expect(saveProfile).toHaveBeenCalledTimes(1));
        expect(saveProfile.mock.calls[0][0]).toMatchObject({ expected_revision: 3, headline: "Principal engineer" });
        expect(saveProfile.mock.calls[0][0].facts[0]).not.toHaveProperty("created_at");
        expect(showToast).toHaveBeenCalledWith(expect.stringContaining("salvato"), "success");
    });

    it("edits detailed career history, compensation, gaps and milestones", async () => {
        render(<CareerProfilePage />);
        const experienceTitle = (await screen.findAllByText("Principal Engineer")).find((element) => element.tagName === "STRONG");
        fireEvent.click(experienceTitle);
        const industry = screen.getByLabelText("Settore");
        fireEvent.change(industry, { target: { value: "Privacy software" } });

        const minimum = screen.getByLabelText("Compenso minimo");
        fireEvent.change(minimum, { target: { value: "160000" } });
        fireEvent.click(screen.getByRole("button", { name: "Aggiungi gap" }));
        fireEvent.change(screen.getByLabelText("Competenza gap 1"), { target: { value: "Budgeting" } });
        fireEvent.click(screen.getByRole("button", { name: "Aggiungi milestone" }));
        fireEvent.change(screen.getByLabelText("Milestone 1"), { target: { value: "Guidare pianificazione annuale" } });
        fireEvent.click(screen.getByRole("button", { name: "Salva Career Vault" }));

        await waitFor(() => expect(saveProfile).toHaveBeenCalledTimes(1));
        const written = saveProfile.mock.calls[0][0];
        expect(written.facts.find((fact) => fact.id === EXPERIENCE_ID).payload).toMatchObject({
            industry: "Privacy software",
            employment_type: "permanent",
            team_size: 12,
        });
        expect(written.goals[0].payload.compensation.minimum).toBe(160000);
        expect(written.goals[0].payload.skill_gaps.at(-1).skill).toBe("Budgeting");
        expect(written.goals[0].payload.milestones.at(-1).title).toBe("Guidare pianificazione annuale");
    });

    it("links skill evidence, records dated achievements and tracks goal progress notes", async () => {
        render(<CareerProfilePage />);

        fireEvent.click(await screen.findByText("Python"));
        fireEvent.click(screen.getByLabelText("Evidenza Principal Engineer"));

        fireEvent.change(screen.getByLabelText("Nuova nota di avanzamento"), { target: { value: "Completato il primo colloquio esplorativo." } });
        fireEvent.click(screen.getByRole("button", { name: "Aggiungi nota di avanzamento" }));

        const typeSelect = screen.getByLabelText("Tipo di fatto da aggiungere");
        fireEvent.change(typeSelect, { target: { value: "achievement" } });
        fireEvent.click(typeSelect.parentElement.querySelector("button"));
        fireEvent.change(screen.getByLabelText("Risultato"), { target: { value: "Riduzione tempi di delivery" } });
        fireEvent.change(screen.getByLabelText("Data risultato"), { target: { value: "2026-06-30" } });
        fireEvent.change(screen.getByLabelText("Dettagli risultato · uno per riga"), { target: { value: "Lead time -40%\nZero regressioni critiche" } });
        fireEvent.click(screen.getByRole("button", { name: "Salva Career Vault" }));

        await waitFor(() => expect(saveProfile).toHaveBeenCalledTimes(1));
        const written = saveProfile.mock.calls[0][0];
        const skill = written.facts.find((fact) => fact.fact_type === "skill");
        const achievement = written.facts.find((fact) => fact.fact_type === "achievement");
        expect(skill.payload.evidence_fact_ids).toEqual([EXPERIENCE_ID]);
        expect(achievement.payload).toMatchObject({
            title: "Riduzione tempi di delivery",
            achieved_on: "2026-06-30",
            details: ["Lead time -40%", "Zero regressioni critiche"],
        });
        expect(written.goals[0].payload.progress_notes[0]).toMatchObject({
            text: "Completato il primo colloquio esplorativo.",
        });
        expect(Date.parse(written.goals[0].payload.progress_notes[0].recorded_at)).not.toBeNaN();
    });
});
