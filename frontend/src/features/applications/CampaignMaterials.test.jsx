import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { assertAccessible } from "../../test/accessibility";
import { renderWithItalian as render } from "../../test/renderWithI18n";
import { CampaignMaterials } from "./CampaignMaterials";

const applicationContext = vi.fn();
const downloadArtifact = vi.fn();

vi.mock("../../services/campaigns", () => ({
    CampaignService: {
        applicationContext: (...args) => applicationContext(...args),
        downloadArtifact: (...args) => downloadArtifact(...args),
    },
}));

function context() {
    return {
        campaign_id: "11111111-1111-4111-8111-111111111111",
        campaign_name: "Spring search",
        application_id: "22222222-2222-4222-8222-222222222222",
        source_application_id: "APP-001",
        source_status: "Applied",
        priority: "High",
        platform: "LinkedIn",
        tracker_record: { Notes: "<img src=x onerror=alert(1)> plain historical note" },
        provenance: { sources: ["tracker", "dossier"] },
        artifact_groups: {
            cv: [{
                id: "33333333-3333-4333-8333-333333333333",
                display_name: "cv.pdf",
                category: "cv",
                media_type: "application/pdf",
                byte_size: 2048,
                download_url: "/api/v1/campaigns/ignored",
            }],
            letter: [{
                id: "44444444-4444-4444-8444-444444444444",
                display_name: "letter.pdf",
                category: "letter",
                media_type: "application/pdf",
                byte_size: 1024,
                download_url: "/api/v1/campaigns/ignored-letter",
            }],
        },
    };
}

describe("CampaignMaterials", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        applicationContext.mockResolvedValue(context());
        downloadArtifact.mockResolvedValue({
            blob: new Blob(["pdf"], { type: "application/pdf" }),
            filename: "cv.pdf",
        });
        vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:campaign-material");
        vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
        vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    });

    it("renders imported context as inert text and downloads through the authenticated service", async () => {
        const user = userEvent.setup();
        const { container } = render(
            <CampaignMaterials applicationId="22222222-2222-4222-8222-222222222222" />,
        );

        expect(await screen.findByRole("heading", { name: "Materiali campagna" })).toBeVisible();
        expect(screen.getByText("Spring search")).toBeVisible();
        expect(screen.getByText("APP-001")).toBeVisible();
        expect(screen.getByText(/<img src=x onerror=alert\(1\)>/)).toBeVisible();
        expect(container.querySelector("img")).toBeNull();
        expect(screen.getByRole("group", { name: "CV" })).toBeVisible();
        expect(screen.getByRole("group", { name: "Lettera" })).toBeVisible();
        await assertAccessible(container);

        await user.click(screen.getByRole("button", { name: /Scarica cv.pdf/ }));
        await waitFor(() => expect(downloadArtifact).toHaveBeenCalledWith(
            "11111111-1111-4111-8111-111111111111",
            "33333333-3333-4333-8333-333333333333",
        ));
        expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:campaign-material");

        downloadArtifact.mockRejectedValueOnce(new Error("C:/Private/material.pdf"));
        await user.click(screen.getByRole("button", { name: /Scarica letter.pdf/ }));
        expect(await screen.findByRole("alert")).toHaveTextContent(
            "Non è stato possibile scaricare il materiale della campagna.",
        );
        expect(screen.queryByText(/Private|material\.pdf/)).toBeNull();
    });

    it("stays absent for a non-campaign application and gives a bounded retry for failures", async () => {
        applicationContext.mockRejectedValueOnce({ status: 404 });
        const { rerender } = render(<CampaignMaterials applicationId="manual-application" />);
        await waitFor(() => expect(applicationContext).toHaveBeenCalledTimes(1));
        expect(screen.queryByRole("heading", { name: "Materiali campagna" })).toBeNull();

        applicationContext.mockRejectedValueOnce(new Error("private tracker detail"));
        rerender(<CampaignMaterials applicationId="campaign-application" />);
        expect(await screen.findByRole("alert")).toHaveTextContent(
            "Non è stato possibile caricare i materiali della campagna.",
        );
        expect(screen.queryByText("private tracker detail")).toBeNull();
        expect(screen.getByRole("button", { name: "Riprova materiali campagna" })).toBeEnabled();
    });
});
