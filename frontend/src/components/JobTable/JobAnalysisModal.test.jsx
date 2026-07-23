import { useState } from "react";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithI18n as render } from "../../test/renderWithI18n";
import { JobAnalysisModal } from "./JobAnalysisModal";

const verifiedJob = {
    id: "job-1",
    title: "Platform Engineer",
    company: "Local Co",
    affinity_score: 92,
    affinity_analysis: "The role matches verified platform work.",
    analysis_verified: true,
    analysis_model_id: "ollama-local/qwen3:1.7b",
    analysis_contract_version: "1.1.0",
    analysis_structured: {
        recommendation: "strong_fit",
        evidence_citations: [{
            type: "skill",
            assessment: "strength",
            job_evidence_id: "job:1",
            candidate_evidence_id: "candidate:1",
            job_evidence: "Production Python",
            candidate_evidence: "Built Python services",
        }],
    },
};

function ModalHarness() {
    const [job, setJob] = useState(null);
    return (
        <>
            <button type="button" onClick={() => setJob(verifiedJob)}>Inspect analysis</button>
            <JobAnalysisModal job={job} onClose={() => setJob(null)} />
        </>
    );
}

describe("JobAnalysisModal", () => {
    it("owns focus, traps it, closes on Escape, restores focus, and locks body scroll", async () => {
        const user = userEvent.setup();
        render(<ModalHarness />);
        const origin = screen.getByRole("button", { name: "Inspect analysis" });

        await user.click(origin);

        const topClose = screen.getByRole("button", { name: "Close match analysis" });
        expect(topClose).toHaveFocus();
        expect(document.body.style.overflow).toBe("hidden");

        await user.tab({ shift: true });
        expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();

        await user.keyboard("{Escape}");
        await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
        expect(origin).toHaveFocus();
        expect(document.body.style.overflow).toBe("");
    });

    it("never renders legacy narrative, score, or citations for an unverified record", () => {
        render(
            <JobAnalysisModal
                job={{ ...verifiedJob, analysis_verified: false }}
                onClose={vi.fn()}
            />
        );

        expect(screen.getByText(/No validated local-model evidence/i)).toBeInTheDocument();
        expect(screen.queryByText("The role matches verified platform work.")).not.toBeInTheDocument();
        expect(screen.queryByText("92%")).not.toBeInTheDocument();
        expect(screen.queryByText("“Production Python”")).not.toBeInTheDocument();
    });
});
