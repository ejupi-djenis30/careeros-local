import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { careerProfile } from "../../test/fixtures";
import { renderWithItalian } from "../../test/renderWithI18n";
import { CareerService } from "../../services/career";
import { CoachService } from "../../services/coach";
import { CareerCoachPage } from "./CareerCoachPage";

const model = vi.hoisted(() => ({ status: { ready: true, loading: false, configured_model: "local-model" }, refresh: vi.fn() }));
vi.mock("../../services/career", () => ({ CareerService: { getProfile: vi.fn() } }));
vi.mock("../../services/coach", () => ({ CoachService: {
    listConversations: vi.fn(), getConversation: vi.fn(), sendMessage: vi.fn(), deleteConversation: vi.fn(),
} }));
vi.mock("../local-model/useLocalModelStatus", () => ({ useLocalModelStatus: () => model }));

const conversation = (id) => ({ id, title: `Conversation ${id}`, updated_at: "2026-10-17T10:00:00Z", message_count: 0, messages: [] });
function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return { promise, resolve, reject };
}
async function openPage() {
    const view = renderWithItalian(<MemoryRouter><CareerCoachPage /></MemoryRouter>);
    await screen.findByLabelText("Messaggio al coach locale");
    return view;
}
const activeTitle = () => document.querySelector(".coach-panel__header strong").textContent;
const choose = (id) => fireEvent.click(screen.getByText(`Conversation ${id}`).closest("button"));
function submit(text = "Synthetic question") {
    const composer = screen.getByLabelText("Messaggio al coach locale");
    fireEvent.change(composer, { target: { value: text } });
    fireEvent.submit(composer.closest("form"));
    return composer;
}

describe("coach conversation and composer ownership", () => {
    beforeEach(() => {
        vi.resetAllMocks();
        model.status.ready = true;
        CareerService.getProfile.mockResolvedValue(careerProfile());
        CoachService.listConversations.mockResolvedValue([conversation("A"), conversation("B")]);
        CoachService.getConversation.mockImplementation(async (id) => conversation(id));
        CoachService.sendMessage.mockResolvedValue({ conversation_id: "A" });
    });

    afterEach(() => { vi.restoreAllMocks(); });

    it("keeps the latest selection when conversation reads resolve out of order", async () => {
        await openPage();
        const first = deferred();
        const second = deferred();
        CoachService.getConversation.mockImplementation((id) => id === "A" ? first.promise : second.promise);
        choose("A");
        choose("B");
        await act(async () => { second.resolve(conversation("B")); await second.promise; });
        expect(activeTitle()).toBe("Conversation B");
        await act(async () => { first.resolve(conversation("A")); await first.promise; });
        expect(activeTitle()).toBe("Conversation B");
    });

    it.each(["new", "B"])("does not let an earlier send replace selection %s or its newer draft", async (target) => {
        await openPage();
        choose("A");
        await waitFor(() => expect(activeTitle()).toBe("Conversation A"));
        const sending = deferred();
        CoachService.sendMessage.mockReturnValueOnce(sending.promise);
        const composer = submit();
        if (target === "new") fireEvent.click(document.querySelector(".coach-conversations > button"));
        else { choose("B"); await waitFor(() => expect(activeTitle()).toBe("Conversation B")); }
        fireEvent.change(composer, { target: { value: "Newer selection draft" } });
        const title = activeTitle();
        await act(async () => { sending.resolve({ conversation_id: "A" }); await sending.promise; });
        expect(activeTitle()).toBe(title);
        expect(composer).toHaveValue("Newer selection draft");
    });

    it("preserves text typed during a successful send and prevents duplicate submission", async () => {
        await openPage();
        const sending = deferred();
        CoachService.sendMessage.mockReturnValueOnce(sending.promise);
        const composer = submit();
        fireEvent.submit(composer.closest("form"));
        fireEvent.change(composer, { target: { value: "Next question draft" } });
        await act(async () => { sending.resolve({ conversation_id: "A" }); await sending.promise; });
        expect(composer).toHaveValue("Next question draft");
        expect(CoachService.sendMessage).toHaveBeenCalledTimes(1);
    });

    it("ignores an old send error after selecting a different conversation", async () => {
        await openPage();
        const sending = deferred();
        CoachService.sendMessage.mockReturnValueOnce(sending.promise);
        submit();
        choose("B");
        await waitFor(() => expect(activeTitle()).toBe("Conversation B"));
        await act(async () => { sending.reject(new Error("Old send failure")); });
        expect(screen.queryByRole("alert")).not.toBeInTheDocument();
        expect(model.refresh).not.toHaveBeenCalled();
    });

    it("does not continue a send or refresh after the page unmounts", async () => {
        const view = await openPage();
        const sending = deferred();
        CoachService.sendMessage.mockReturnValueOnce(sending.promise);
        submit();
        view.unmount();
        await act(async () => { sending.resolve({ conversation_id: "A" }); await sending.promise; });
        expect(CoachService.getConversation).not.toHaveBeenCalled();
        expect(CoachService.listConversations).toHaveBeenCalledTimes(1);
        expect(CoachService.sendMessage.mock.calls[0][1].signal.aborted).toBe(true);
    });

    it("retains the draft on a real send failure and retries only after another explicit submission", async () => {
        await openPage();
        CoachService.sendMessage.mockRejectedValueOnce(new Error("Local model request failed"));
        const composer = submit();
        expect(await screen.findByRole("alert")).toHaveTextContent("Local model request failed");
        expect(composer).toHaveValue("Synthetic question");
        expect(CoachService.sendMessage).toHaveBeenCalledTimes(1);
        fireEvent.submit(composer.closest("form"));
        await waitFor(() => expect(activeTitle()).toBe("Conversation A"));
        expect(CoachService.sendMessage).toHaveBeenCalledTimes(2);
        expect(composer).toHaveValue("");
    });

    it("retries the conversation read after an acknowledged send without sending the message twice", async () => {
        await openPage();
        CoachService.getConversation.mockRejectedValueOnce(new Error("Conversation read failed"));
        const composer = submit();
        expect(await screen.findByRole("alert")).toHaveTextContent("Conversation read failed");
        fireEvent.change(composer, { target: { value: "Later draft" } });
        fireEvent.click(screen.getByRole("button", { name: "Riprova" }));
        await waitFor(() => expect(activeTitle()).toBe("Conversation A"));
        expect(CoachService.sendMessage).toHaveBeenCalledTimes(1);
        expect(composer).toHaveValue("Later draft");
        expect(model.refresh).not.toHaveBeenCalled();
    });

    it("retries only the catalog when that read fails after a confirmed send and conversation read", async () => {
        await openPage();
        CoachService.listConversations.mockRejectedValueOnce(new Error("Catalog read failed"));
        const composer = submit();
        expect(await screen.findByRole("alert")).toHaveTextContent("Catalog read failed");
        fireEvent.change(composer, { target: { value: "Next draft" } });
        fireEvent.click(screen.getByRole("button", { name: "Riprova" }));
        await waitFor(() => expect(CoachService.listConversations).toHaveBeenCalledTimes(3));
        expect(CoachService.getConversation).toHaveBeenCalledTimes(1);
        expect(CoachService.sendMessage).toHaveBeenCalledTimes(1);
        expect(composer).toHaveValue("Next draft");
        expect(model.refresh).not.toHaveBeenCalled();
    });

    it("does not clear a newer selection when deleting the previous conversation completes", async () => {
        vi.spyOn(window, "confirm").mockReturnValue(true);
        await openPage();
        choose("A");
        await waitFor(() => expect(activeTitle()).toBe("Conversation A"));
        const deleting = deferred();
        CoachService.deleteConversation.mockReturnValueOnce(deleting.promise);
        fireEvent.click(screen.getByRole("button", { name: "Elimina Conversation A" }));
        choose("B");
        await waitFor(() => expect(activeTitle()).toBe("Conversation B"));
        CoachService.listConversations.mockResolvedValueOnce([conversation("B")]);
        await act(async () => { deleting.resolve(); await deleting.promise; });
        expect(activeTitle()).toBe("Conversation B");
        expect(screen.queryByText("Conversation A")).not.toBeInTheDocument();
    });

    it("initializes through StrictMode cleanup and never sends into a conversation still being loaded", async () => {
        renderWithItalian(<StrictMode><MemoryRouter><CareerCoachPage /></MemoryRouter></StrictMode>);
        await screen.findByLabelText("Messaggio al coach locale");
        const loading = deferred();
        CoachService.getConversation.mockReturnValueOnce(loading.promise);
        choose("B");
        const composer = submit();
        expect(CoachService.sendMessage).not.toHaveBeenCalled();
        await act(async () => { loading.resolve(conversation("B")); await loading.promise; });
        expect(activeTitle()).toBe("Conversation B");
        fireEvent.submit(composer.closest("form"));
        await waitFor(() => expect(CoachService.sendMessage).toHaveBeenCalledTimes(1));
        expect(CoachService.sendMessage.mock.calls[0][0].conversation_id).toBe("B");
    });

    it("retries an initial profile read without requiring a local model", async () => {
        model.status.ready = false;
        CareerService.getProfile.mockRejectedValueOnce(new Error("Profile read failed"));
        renderWithItalian(<MemoryRouter><CareerCoachPage /></MemoryRouter>);
        expect(await screen.findByRole("alert")).toHaveTextContent("Profile read failed");
        fireEvent.click(screen.getByRole("button", { name: "Riprova" }));
        const composer = await screen.findByLabelText("Messaggio al coach locale");
        fireEvent.change(composer, { target: { value: "Synthetic question" } });
        fireEvent.submit(composer.closest("form"));
        expect(CareerService.getProfile).toHaveBeenCalledTimes(2);
        expect(CoachService.sendMessage).not.toHaveBeenCalled();
    });
});
