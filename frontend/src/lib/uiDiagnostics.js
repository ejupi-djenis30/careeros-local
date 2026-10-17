const operationCodes = new Set([
    "react_caught", "react_uncaught", "react_recoverable",
    "jobs_fetch", "jobs_profiles", "jobs_undo", "jobs_dismiss", "jobs_reactivate",
    "search_poll", "history_profiles", "schedules_profiles", "search_stop",
    "progress_profiles", "job_view", "auth_expired",
]);

export function reportUiFailure(operation) {
    const code = operationCodes.has(operation) ? operation : "unknown";
    const message = `ui_failure code=${code}`;
    if (code === "job_view" || code === "auth_expired") console.warn(message);
    else console.error(message);
}

export const reactErrorHandlers = Object.freeze({
    onCaughtError: () => reportUiFailure("react_caught"),
    onUncaughtError: () => reportUiFailure("react_uncaught"),
    onRecoverableError: () => reportUiFailure("react_recoverable"),
});
