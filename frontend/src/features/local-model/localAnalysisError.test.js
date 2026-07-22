import { describe, expect, it } from "vitest";

import { createTranslator } from "../../i18n/runtime";
import { describeLocalAnalysisError, localAnalysisErrorCode } from "./localAnalysisError";

describe("local analysis error presentation", () => {
    it("maps a structured 428 response to actionable localized copy", () => {
        const error = {
            status: 428,
            details: {
                detail: {
                    code: "local_model_required",
                    message: "internal English fallback",
                    model_error_code: "configured_model_missing",
                },
            },
        };

        expect(localAnalysisErrorCode(error)).toBe("local_model_required");
        expect(describeLocalAnalysisError(error, createTranslator("it"))).toMatch(/Apri Oggi.*Installa o seleziona/i);
        expect(describeLocalAnalysisError(error, createTranslator("en"))).not.toContain("{");
    });

    it("maps a terminal local analysis failure without exposing transport details", () => {
        const error = { details: { detail: { code: "local_analysis_failed" } } };
        expect(describeLocalAnalysisError(error, createTranslator("en"))).toMatch(/saved no substitute score/i);
    });
});
