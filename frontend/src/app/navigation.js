export const NAVIGATION = [
    {
        label: "Career workspace",
        items: [
            { to: "/", label: "Oggi", icon: "bi-house-door" },
            { to: "/profile", label: "Career Vault", icon: "bi-person-vcard" },
            { to: "/resumes", label: "CV Studio", icon: "bi-file-earmark-person" },
            { to: "/applications", label: "Candidature", icon: "bi-kanban" },
            { to: "/coach", label: "Coach locale", icon: "bi-chat-square-text" },
        ],
    },
    {
        label: "Opportunità",
        items: [
            { to: "/jobs", label: "Annunci", icon: "bi-briefcase" },
            { to: "/search", label: "Nuova ricerca", icon: "bi-radar" },
            { to: "/progress", label: "Attività", icon: "bi-activity" },
            { to: "/history", label: "Cronologia", icon: "bi-clock-history" },
            { to: "/schedules", label: "Pianificazioni", icon: "bi-calendar2-week" },
        ],
    },
];

export const PAGE_CONTEXT = {
    "/": { eyebrow: "CareerOS Local", title: "Il tuo spazio carriera", description: "Dati, decisioni e prossime mosse. Tutto sul tuo dispositivo." },
    "/profile": { eyebrow: "Fonte di verità", title: "Career Vault", description: "Il profilo completo da cui nascono CV, matching e coaching." },
    "/resumes": { eyebrow: "Documenti verificabili", title: "CV Studio", description: "Crea CV ATS o con foto, versionati e pronti da inviare." },
    "/applications": { eyebrow: "Pipeline personale", title: "Candidature", description: "Mantieni uno storico immutabile di ogni opportunità." },
    "/coach": { eyebrow: "Ollama · solo locale", title: "Coach carriera", description: "Ragiona sui fatti che scegli, con citazioni verificabili." },
    "/jobs": { eyebrow: "Opportunity engine", title: "Annunci", description: "Valuta e organizza le opportunità raccolte." },
    "/search": { eyebrow: "Opportunity engine", title: "Nuova ricerca", description: "Configura una ricerca mirata con fallback deterministico." },
    "/progress": { eyebrow: "Workflow", title: "Attività", description: "Stato e log delle ricerche in corso." },
    "/history": { eyebrow: "Archivio", title: "Cronologia ricerche", description: "Rivedi le esecuzioni precedenti." },
    "/schedules": { eyebrow: "Automazioni locali", title: "Pianificazioni", description: "Gestisci le ricerche programmate." },
};

