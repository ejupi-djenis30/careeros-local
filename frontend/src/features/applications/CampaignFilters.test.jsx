import { useState } from "react";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { assertAccessible } from "../../test/accessibility";
import { renderWithItalian as render } from "../../test/renderWithI18n";
import { CampaignFilters } from "./CampaignFilters";

describe("CampaignFilters", () => {
    it("exposes bounded campaign, text, stage and priority controls", async () => {
        const user = userEvent.setup();
        const onChange = vi.fn();
        function Harness() {
            const [filters, setFilters] = useState({
                campaignId: "", query: "", stage: "", priority: "",
            });
            const update = (next) => {
                setFilters(next);
                onChange(next);
            };
            return (
                <CampaignFilters
                    campaigns={[{ id: "campaign-1", name: "Spring search" }]}
                    filters={filters}
                    onChange={update}
                />
            );
        }
        const { container } = render(
            <Harness />,
        );

        const query = screen.getByLabelText("Cerca nelle candidature");
        expect(query).toHaveAttribute("maxlength", "200");
        await user.type(query, "platform");
        expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ query: "platform" }));

        await user.selectOptions(screen.getByLabelText("Campagna"), "campaign-1");
        expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({
            campaignId: "campaign-1",
        }));
        await user.selectOptions(screen.getByLabelText("Fase"), "applied");
        expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ stage: "applied" }));
        await user.selectOptions(screen.getByLabelText("Priorità"), "High");
        expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ priority: "High" }));
        expect(screen.getByRole("option", { name: "Urgente" })).toHaveValue("Urgent");
        expect(screen.getByRole("option", { name: "Alta" })).toHaveValue("High");
        expect(screen.getByRole("option", { name: "Media" })).toHaveValue("Medium");
        expect(screen.getByRole("option", { name: "Bassa" })).toHaveValue("Low");
        await assertAccessible(container);
    });
});
