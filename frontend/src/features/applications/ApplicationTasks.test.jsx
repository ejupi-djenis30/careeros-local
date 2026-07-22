import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { application } from "../../test/fixtures";
import { renderWithItalian as render } from "../../test/renderWithI18n";
import { ApplicationTasks } from "./ApplicationTasks";

const createTask = vi.fn();
const updateTask = vi.fn();
const downloadTaskCalendar = vi.fn();
const saveBlob = vi.fn();

vi.mock("../../services/applications", () => ({ ApplicationService: {
    createTask: (...args) => createTask(...args),
    updateTask: (...args) => updateTask(...args),
    downloadTaskCalendar: (...args) => downloadTaskCalendar(...args),
} }));
vi.mock("../../lib/download", () => ({ saveBlob: (...args) => saveBlob(...args) }));

describe("ApplicationTasks", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        createTask.mockResolvedValue(application({ revision: 2 }));
        updateTask.mockResolvedValue(application({ revision: 3 }));
        downloadTaskCalendar.mockResolvedValue({ blob: new Blob(), filename: "tasks.ics" });
    });

    it("creates a dated next action with a local calendar reminder", async () => {
        const user = userEvent.setup();
        const onChanged = vi.fn();
        render(<ApplicationTasks application={application({ tasks: [] })} onChanged={onChanged} />);

        await user.type(screen.getByLabelText("Azione"), "Invia candidatura personalizzata");
        await user.type(screen.getByLabelText("Scadenza"), "2026-08-01T09:00");
        await user.selectOptions(screen.getByLabelText("Priorità"), "high");
        await user.selectOptions(screen.getByLabelText("Promemoria calendario"), "30");
        await user.click(screen.getByRole("button", { name: "Aggiungi prossima azione" }));

        await waitFor(() => expect(createTask).toHaveBeenCalledWith(
            "44444444-4444-4444-8444-444444444444",
            expect.objectContaining({
                expected_revision: 1,
                title: "Invia candidatura personalizzata",
                priority: "high",
            }),
        ));
        const payload = createTask.mock.calls[0][1];
        expect(new Date(payload.due_at).getTime() - new Date(payload.reminder_at).getTime()).toBe(30 * 60_000);
        expect(onChanged).toHaveBeenCalledTimes(1);
    });

    it("completes an action and exports dated pending tasks", async () => {
        const user = userEvent.setup();
        const task = {
            id: "task-1",
            title: "Research the team",
            status: "pending",
            priority: "normal",
            due_at: "2026-08-01T09:00:00Z",
            reminder_at: null,
            completed_at: null,
            revision: 1,
            created_at: "2026-07-20T09:00:00Z",
            updated_at: "2026-07-20T09:00:00Z",
        };
        const onChanged = vi.fn();
        render(<ApplicationTasks application={application({ tasks: [task] })} onChanged={onChanged} />);

        await user.click(screen.getByRole("button", { name: "Completa" }));
        expect(updateTask).toHaveBeenCalledWith(application().id, task.id, {
            expected_revision: 1,
            status: "completed",
        });
        await user.click(screen.getByRole("button", { name: "Esporta calendario" }));
        await waitFor(() => expect(saveBlob).toHaveBeenCalledTimes(1));
    });
});
