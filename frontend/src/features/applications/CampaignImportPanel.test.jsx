import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { assertAccessible } from "../../test/accessibility";
import { renderWithItalian as render } from "../../test/renderWithI18n";
import { CampaignImportPanel } from "./CampaignImportPanel";

const preview = vi.fn();
const importArchive = vi.fn();
const isDesktopShell = vi.fn();
const openCampaignWithNativeDialog = vi.fn();

vi.mock("../../services/campaigns", () => ({
    CampaignService: {
        preview: (...args) => preview(...args),
        importArchive: (...args) => importArchive(...args),
    },
}));
vi.mock("../../platform/desktop", () => ({
    isDesktopShell: () => isDesktopShell(),
    openCampaignWithNativeDialog: (...args) => openCampaignWithNativeDialog(...args),
}));

function previewResponse(overrides = {}) {
    return {
        fingerprint: "a".repeat(64),
        suggested_name: "Legacy application campaign",
        suggested_profile_name: "Fictional Candidate",
        tracker_rows: 4,
        dossier_count: 3,
        matched_count: 2,
        tracker_only_count: 2,
        dossier_only_count: 1,
        logical_application_count: 5,
        artifact_count: 16,
        expanded_bytes: 12345,
        status_counts: { Applied: 1, Closed: 1, Preparing: 1, Saved: 1 },
        credential_rows_omitted: 2,
        warnings: ["Credential rows were omitted."],
        sample: [],
        requires_profile_name: true,
        ...overrides,
    };
}

describe("CampaignImportPanel", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        isDesktopShell.mockReturnValue(false);
        preview.mockResolvedValue(previewResponse());
        importArchive.mockResolvedValue({
            campaign_id: "11111111-1111-4111-8111-111111111111",
            created: true,
            application_count: 5,
        });
    });

    it("previews a browser-selected ZIP without displaying its private filename", async () => {
        const user = userEvent.setup();
        const file = new File(["PK"], "Candidate Name private search.zip", {
            type: "application/zip",
        });
        const { container } = render(<CampaignImportPanel onImported={vi.fn()} />);

        const input = screen.getByLabelText("Archivio ZIP della campagna");
        expect(input).toHaveAttribute("accept", ".zip,application/zip");
        expect(input).toHaveAttribute("tabindex", "-1");
        await user.upload(input, file);

        expect(await screen.findByRole("heading", { name: "Anteprima campagna" })).toBeVisible();
        expect(preview).toHaveBeenCalledWith(file);
        expect(screen.getByText(/5 candidature/)).toBeVisible();
        expect(screen.getByText(/16 materiali/)).toBeVisible();
        expect(screen.getByText(/Righe tracker:\s*4/i)).toBeVisible();
        expect(screen.getByText(/Dossier:\s*3/i)).toBeVisible();
        expect(screen.getByText(/Abbinamenti:\s*2/i)).toBeVisible();
        expect(screen.getByText(/Solo tracker:\s*2/i)).toBeVisible();
        expect(screen.getByText(/Solo dossier:\s*1/i)).toBeVisible();
        expect(screen.getByRole("heading", { name: "Stati originali" })).toBeVisible();
        expect(screen.getByText(/Applied:\s*1/)).toBeVisible();
        expect(screen.getByText(/2 righe credenziali escluse/)).toBeVisible();
        expect(screen.getByText(/non è cifrato/i)).toBeVisible();
        expect(screen.queryByText("Candidate Name private search.zip")).toBeNull();
        expect(screen.getByRole("button", { name: /Importa 5 candidature/ })).toBeDisabled();
        await assertAccessible(container);
    });

    it("requires profile bootstrap, imports the exact previewed file and refreshes the owner view", async () => {
        const user = userEvent.setup();
        const onImported = vi.fn();
        const file = new File(["PK"], "campaign.zip", { type: "application/zip" });
        render(<CampaignImportPanel onImported={onImported} />);

        await user.upload(screen.getByLabelText("Archivio ZIP della campagna"), file);
        await screen.findByRole("heading", { name: "Anteprima campagna" });
        expect(screen.getByLabelText("Nome campagna")).toHaveValue(
            "Legacy application campaign",
        );
        expect(screen.getByLabelText("Nome del profilo")).toHaveValue("Fictional Candidate");
        await user.clear(screen.getByLabelText("Nome del profilo"));
        expect(screen.getByRole("button", { name: /Importa 5 candidature/ })).toBeDisabled();
        await user.type(screen.getByLabelText("Nome del profilo"), "Local Owner");
        await user.click(screen.getByRole("button", { name: /Importa 5 candidature/ }));

        await waitFor(() => expect(importArchive).toHaveBeenCalledWith(file, {
            expectedFingerprint: "a".repeat(64),
            name: "Legacy application campaign",
            profileDisplayName: "Local Owner",
        }));
        expect(onImported).toHaveBeenCalledWith(expect.objectContaining({
            campaign_id: "11111111-1111-4111-8111-111111111111",
            created: true,
        }));
        expect(await screen.findByRole("status")).toHaveTextContent(/5 candidature importate/i);
        expect(screen.queryByText("campaign.zip")).toBeNull();
    });

    it("uses one native picker at a time and recovers from a local picker error", async () => {
        const user = userEvent.setup();
        isDesktopShell.mockReturnValue(true);
        let rejectSelection;
        openCampaignWithNativeDialog.mockReturnValue(new Promise((_resolve, reject) => {
            rejectSelection = reject;
        }));
        render(<CampaignImportPanel onImported={vi.fn()} />);
        const choose = screen.getByRole("button", { name: "Scegli archivio campagna" });

        await user.click(choose);
        await user.click(choose);
        expect(openCampaignWithNativeDialog).toHaveBeenCalledTimes(1);
        expect(openCampaignWithNativeDialog).toHaveBeenCalledWith({
            title: "Apri archivio campagna CareerOS",
        });
        rejectSelection(new Error("private native path"));

        expect(await screen.findByRole("alert")).toHaveTextContent(
            "Non è stato possibile aprire l’archivio della campagna.",
        );
        expect(screen.queryByText("private native path")).toBeNull();
        await waitFor(() => expect(choose).toBeEnabled());
    });

    it("keeps import errors bounded and permits choosing another archive", async () => {
        const user = userEvent.setup();
        preview.mockRejectedValue(new Error("C:/Private/User/source.zip contains secret cell"));
        render(<CampaignImportPanel onImported={vi.fn()} />);

        await user.upload(
            screen.getByLabelText("Archivio ZIP della campagna"),
            new File(["bad"], "secret-name.zip", { type: "application/zip" }),
        );

        expect(await screen.findByRole("alert")).toHaveTextContent(
            "Non è stato possibile verificare l’archivio della campagna.",
        );
        expect(screen.queryByText(/Private|secret cell|secret-name/i)).toBeNull();
        expect(screen.getByRole("button", { name: "Scegli archivio campagna" })).toBeEnabled();
    });

    it("keeps a failed import preview available for a bounded retry", async () => {
        const user = userEvent.setup();
        importArchive.mockRejectedValue(new Error("C:/Private/User/source.zip leaked detail"));
        render(<CampaignImportPanel onImported={vi.fn()} />);

        await user.upload(
            screen.getByLabelText("Archivio ZIP della campagna"),
            new File(["PK"], "private-campaign.zip", { type: "application/zip" }),
        );
        await screen.findByRole("heading", { name: "Anteprima campagna" });
        await user.clear(screen.getByLabelText("Nome del profilo"));
        await user.type(screen.getByLabelText("Nome del profilo"), "Local Owner");
        await user.click(screen.getByRole("button", { name: /Importa 5 candidature/ }));

        expect(await screen.findByRole("alert")).toHaveTextContent(
            "Non è stato possibile importare la campagna.",
        );
        expect(screen.queryByText(/Private|leaked detail|private-campaign/i)).toBeNull();
        expect(screen.getByRole("heading", { name: "Anteprima campagna" })).toBeVisible();
        expect(screen.getByRole("button", { name: /Importa 5 candidature/ })).toBeEnabled();
    });
});
