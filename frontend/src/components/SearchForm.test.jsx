import { MemoryRouter } from "react-router";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SearchForm } from "./SearchForm";
import { careerProfile } from "../test/fixtures";
import { renderWithI18n as render } from "../test/renderWithI18n";
import { assertAccessible } from "../test/accessibility";

const mocks = vi.hoisted(() => ({
    getProfile: vi.fn(),
    getProfileSummaries: vi.fn(),
    uploadCV: vi.fn(),
    showToast: vi.fn(),
}));

vi.mock("../services/career", () => ({
    CareerService: { getProfile: mocks.getProfile },
}));

vi.mock("../services/search", () => ({
    SearchService: {
        getProfileSummaries: mocks.getProfileSummaries,
        uploadCV: mocks.uploadCV,
    },
}));

vi.mock("../context/ToastContext", () => ({
    useToast: () => ({ showToast: mocks.showToast }),
}));

function renderForm(props = {}) {
    const onStartSearch = props.onStartSearch || vi.fn().mockResolvedValue({ ok: true });
    const result = render(
        <MemoryRouter>
            <SearchForm onStartSearch={onStartSearch} isLoading={false} {...props} />
        </MemoryRouter>,
    );
    return { ...result, onStartSearch };
}

async function completeRequiredFields(user) {
    await user.type(screen.getByLabelText(/Role description/i), "Senior backend engineer working with Python");
    await user.type(screen.getByLabelText(/Target location/i), "Zurich");
}

describe("SearchForm profile source workflow", () => {
    beforeEach(() => {
        mocks.getProfile.mockReset().mockResolvedValue(careerProfile());
        mocks.getProfileSummaries.mockReset().mockResolvedValue([]);
        mocks.uploadCV.mockReset();
        mocks.showToast.mockReset();
    });

    it("uses a ready Career Vault by default and omits CV content", async () => {
        const user = userEvent.setup();
        const { onStartSearch } = renderForm();

        expect(screen.getByRole("radio", { name: /Career Vault/i })).toBeChecked();
        expect(await screen.findByText("Revision 3")).toBeInTheDocument();
        expect(screen.getByText("2 confirmed facts")).toBeInTheDocument();

        await completeRequiredFields(user);
        await user.click(screen.getByRole("button", { name: "Start search" }));

        await waitFor(() => expect(onStartSearch).toHaveBeenCalledTimes(1));
        const payload = onStartSearch.mock.calls[0][0];
        expect(payload.profile_source).toBe("career_vault");
        expect(payload).not.toHaveProperty("cv_content");
    });

    it("links to the vault and focuses its source option when confirmed facts are missing", async () => {
        const user = userEvent.setup();
        mocks.getProfile.mockResolvedValue(careerProfile({ facts: [] }));
        const { onStartSearch } = renderForm();

        const vaultLink = await screen.findByRole("link", { name: /Open Career Vault/i });
        expect(vaultLink).toHaveAttribute("href", "/profile");
        await completeRequiredFields(user);
        await user.click(screen.getByRole("button", { name: "Start search" }));

        expect(await screen.findByText(/Add and confirm at least one fact/i)).toBeInTheDocument();
        await waitFor(() => expect(screen.getByRole("radio", { name: /Career Vault/i })).toHaveFocus());
        expect(onStartSearch).not.toHaveBeenCalled();
    });

    it("supports an uploaded CV as an explicit alternative", async () => {
        const user = userEvent.setup();
        mocks.uploadCV.mockResolvedValue({ text: "CV body" });
        const { onStartSearch } = renderForm();

        await user.click(screen.getByRole("radio", { name: /Uploaded CV/i }));
        const file = new File(["resume"], "resume.pdf", { type: "application/pdf" });
        await user.upload(screen.getByLabelText("Select"), file);
        expect(await screen.findByText("CV ready for this search")).toBeInTheDocument();

        await completeRequiredFields(user);
        await user.click(screen.getByRole("button", { name: "Start search" }));

        await waitFor(() => expect(onStartSearch).toHaveBeenCalledTimes(1));
        expect(onStartSearch.mock.calls[0][0]).toMatchObject({
            profile_source: "uploaded_cv",
            cv_content: "CV body",
        });
    });

    it("normalizes remote-only searches and disables distance controls", async () => {
        const user = userEvent.setup();
        const { onStartSearch } = renderForm();
        await screen.findByText("Revision 3");
        await completeRequiredFields(user);
        await user.click(screen.getByRole("switch", { name: /Remote only/i }));
        await user.click(screen.getByText("Advanced settings"));

        expect(screen.getByLabelText("Maximum distance")).toBeDisabled();
        await user.click(screen.getByRole("button", { name: "Start search" }));

        await waitFor(() => expect(onStartSearch).toHaveBeenCalledTimes(1));
        expect(onStartSearch.mock.calls[0][0]).toMatchObject({
            remote_only: true,
            max_distance: 0,
        });
    });

    it("focuses the first invalid field and exposes no automated accessibility violations", async () => {
        const user = userEvent.setup();
        const { container, onStartSearch } = renderForm();
        await screen.findByText("Revision 3");

        await user.click(screen.getByRole("button", { name: "Start search" }));
        expect(await screen.findByText("Describe the role you are looking for.")).toBeInTheDocument();
        await waitFor(() => expect(screen.getByLabelText(/Role description/i)).toHaveFocus());
        expect(onStartSearch).not.toHaveBeenCalled();
        await assertAccessible(container);
    });

    it("validates a history template with nullable fields without throwing", async () => {
        const user = userEvent.setup();
        const { onStartSearch } = renderForm({
            prefill: {
                id: 42,
                name: null,
                role_description: "Backend engineer",
                location_filter: null,
                cv_content: null,
                search_strategy: null,
                workload_filter: null,
                contract_type: null,
                profile_source: "career_vault",
            },
        });
        await screen.findByText("Revision 3");

        await user.click(screen.getByRole("button", { name: "Start search" }));

        expect(await screen.findByText("Enter a target location.")).toBeInTheDocument();
        await waitFor(() => expect(screen.getByLabelText(/Target location/i)).toHaveFocus());
        expect(onStartSearch).not.toHaveBeenCalled();
    });
});
