import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { careerProfile, FACT_ID, PROFILE_ID } from "../../test/fixtures";
import { renderWithItalian as render } from "../../test/renderWithI18n";
import { CareerCoachPage } from "./CareerCoachPage";

const sendMessage = vi.fn();
const getConversation = vi.fn();
const listConversations = vi.fn();
const refreshModel = vi.fn();

vi.mock("../../services/career", () => ({ CareerService: { getProfile: vi.fn(async () => careerProfile()) } }));
vi.mock("../../services/coach", () => ({ CoachService: { listConversations: (...args) => listConversations(...args), getConversation: (...args) => getConversation(...args), sendMessage: (...args) => sendMessage(...args), deleteConversation: vi.fn() } }));
vi.mock("../local-model/useLocalModelStatus", () => ({ useLocalModelStatus: () => ({ status: { loading: false, available: true, ready: true, configured_model: "qwen3:4b" }, refresh: refreshModel }) }));

describe("CareerCoachPage", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        listConversations.mockResolvedValue([]);
        sendMessage.mockResolvedValue({ conversation_id: "conversation-1", message: {} });
        getConversation.mockResolvedValue({ id: "conversation-1", profile_id: PROFILE_ID, title: "Punti forti", created_at: "2026-01-01T10:00:00Z", updated_at: "2026-01-01T10:00:00Z", messages: [{ id: "m1", role: "assistant", content: "Python è un punto forte verificato.", cited_fact_ids: [FACT_ID], cited_job_ids: [], model_id: "qwen3:4b", generation_metadata: {}, created_at: "2026-01-01T10:00:00Z" }] });
    });

    it("sends only explicitly selected career facts to the local coach", async () => {
        const user = userEvent.setup();
        render(<CareerCoachPage />);
        const composer = await screen.findByLabelText("Messaggio al coach locale");
        await user.click(screen.getByText("Contesto esplicito"));
        await user.click(screen.getByRole("checkbox", { name: /Python/ }));
        await user.type(composer, "Qual è il mio punto forte?");
        await user.click(screen.getByRole("button", { name: /Invia/ }));

        await waitFor(() => expect(sendMessage).toHaveBeenCalledWith({ conversation_id: null, message: "Qual è il mio punto forte?", fact_ids: [FACT_ID], job_ids: [] }));
        expect(await screen.findByText("Python è un punto forte verificato.")).toBeInTheDocument();
        expect(screen.getByText(`fatto ${FACT_ID.slice(0, 8)}`)).toBeInTheDocument();
    });
});
