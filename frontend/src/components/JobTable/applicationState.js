const APPLICATION_STAGES = new Set([
    "preparing",
    "applied",
    "screening",
    "interview",
    "offer",
    "accepted",
    "rejected",
    "withdrawn",
    "archived",
]);

function cleanIdentifier(value) {
    if (value == null) return "";
    return String(value).trim();
}

export function getJobApplicationState(job, t) {
    const applicationId = cleanIdentifier(job?.application_id);

    if (applicationId) {
        const stage = cleanIdentifier(job?.application_stage).toLowerCase();
        const knownStage = APPLICATION_STAGES.has(stage);

        return {
            applicationId,
            action: t("jobs.openApplication"),
            className: knownStage ? stage : "tracked",
            href: `/applications?applicationId=${encodeURIComponent(applicationId)}`,
            icon: "bi-folder2-open",
            label: knownStage ? t(`stage.${stage}`) : t("jobs.applicationStage.tracked"),
            legacy: false,
            tracked: true,
        };
    }

    const legacy = job?.applied === true || job?.applied_elsewhere === true;
    const jobId = cleanIdentifier(job?.id);

    return {
        applicationId: "",
        action: t("jobs.trackApplication"),
        className: legacy ? "legacy" : "untracked",
        href: jobId ? `/applications?jobId=${encodeURIComponent(jobId)}` : "/applications",
        icon: "bi-kanban",
        label: legacy ? t("jobs.applicationStage.legacy") : t("jobs.applicationStage.untracked"),
        legacy,
        tracked: false,
    };
}
