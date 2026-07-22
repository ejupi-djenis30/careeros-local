import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderWithI18n as render } from "../../test/renderWithI18n";
import { SearchFormAdvanced } from "./SearchFormAdvanced";


function profile(overrides = {}) {
    return {
        id: null,
        name: "",
        schedule_enabled: false,
        schedule_interval_hours: 24,
        max_queries: "",
        max_occupation_queries: "",
        max_keyword_queries: "",
        force_regenerate_cv_summary: false,
        force_regenerate_queries: false,
        ...overrides,
    };
}


describe("SearchFormAdvanced deterministic query limits", () => {
    it("allows zero and explains blank as a deterministic default", () => {
        const { container } = render(<SearchFormAdvanced
            profile={profile()}
            handleChange={vi.fn()}
            setProfile={vi.fn()}
        />);

        const maximum = container.querySelector('input[name="max_queries"]');
        const occupations = container.querySelector('input[name="max_occupation_queries"]');
        const keywords = container.querySelector('input[name="max_keyword_queries"]');
        expect(maximum).toHaveAttribute("min", "0");
        expect(maximum).toHaveAttribute("placeholder", "Use default");
        expect(occupations).toHaveAttribute("placeholder", "Use default");
        expect(keywords).toHaveAttribute("placeholder", "Use default");
        expect(screen.getByText(/Set 0 to disable all queries/i)).toBeInTheDocument();
        expect(screen.queryByText(/AI decides/i)).not.toBeInTheDocument();
    });
});
