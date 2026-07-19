export function getNavigation(t) {
    return [
        {
            label: t("nav.group.workspace"),
            items: [
                { to: "/", label: t("nav.today"), icon: "bi-house-door" },
                { to: "/profile", label: t("nav.vault"), icon: "bi-person-vcard" },
                { to: "/resumes", label: t("nav.resumes"), icon: "bi-file-earmark-person" },
                { to: "/applications", label: t("nav.applications"), icon: "bi-kanban" },
                { to: "/coach", label: t("nav.coach"), icon: "bi-chat-square-text" },
            ],
        },
        {
            label: t("nav.group.opportunities"),
            items: [
                { to: "/jobs", label: t("nav.jobs"), icon: "bi-briefcase" },
                { to: "/search", label: t("nav.search"), icon: "bi-radar" },
                { to: "/progress", label: t("nav.progress"), icon: "bi-activity" },
                { to: "/history", label: t("nav.history"), icon: "bi-clock-history" },
                { to: "/schedules", label: t("nav.schedules"), icon: "bi-calendar2-week" },
            ],
        },
    ];
}

export function getPageContext(pathname, t) {
    const pages = {
        "/": "home",
        "/profile": "profile",
        "/resumes": "resumes",
        "/applications": "applications",
        "/coach": "coach",
        "/jobs": "jobs",
        "/search": "search",
        "/progress": "progress",
        "/history": "history",
        "/schedules": "schedules",
    };
    const page = pages[pathname] || "home";
    return {
        eyebrow: t(`page.${page}.eyebrow`),
        title: t(`page.${page}.title`),
        description: t(`page.${page}.description`),
    };
}
