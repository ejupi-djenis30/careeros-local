const READINESS_CODES = new Set([
    "local_runtime_unreachable",
    "configured_model_missing",
    "structured_probe_timeout",
    "structured_probe_failed",
    "readiness_service_unreachable",
]);

function errorDetail(error) {
    const detail = error?.details?.detail ?? error?.details;
    if (detail && typeof detail === "object" && !Array.isArray(detail)) return detail;
    return {};
}

export function localAnalysisErrorCode(error) {
    const detail = errorDetail(error);
    return detail.code || detail.error_code || error?.code || "";
}

export function describeLocalAnalysisError(error, t) {
    const detail = errorDetail(error);
    const code = localAnalysisErrorCode(error);

    if (error?.status === 428 || code === "local_model_required") {
        const readinessCode = detail.model_error_code;
        const diagnostic = READINESS_CODES.has(readinessCode)
            ? t(`analysisGate.error.${readinessCode}`)
            : t("analysisGate.error.unknown");
        return `${t("analysisError.localModelRequired")} ${diagnostic}`;
    }
    if (code === "local_analysis_failed") {
        return t("analysisError.localAnalysisFailed");
    }
    return null;
}
