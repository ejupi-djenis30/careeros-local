export const STAGES = ["saved", "preparing", "applied", "screening", "interview", "offer", "accepted", "rejected", "withdrawn", "archived"];

export const STAGE_LABELS = {
    saved: "Salvata",
    preparing: "Preparazione",
    applied: "Inviata",
    screening: "Screening",
    interview: "Colloquio",
    offer: "Offerta",
    accepted: "Accettata",
    rejected: "Rifiutata",
    withdrawn: "Ritirata",
    archived: "Archiviata",
};

export function getStageLabels(t) {
    return Object.fromEntries(STAGES.map((stage) => [stage, t(`stage.${stage}`)]));
}

export const TRANSITIONS = {
    saved: ["preparing", "applied", "withdrawn", "archived"],
    preparing: ["saved", "applied", "withdrawn", "archived"],
    applied: ["screening", "interview", "rejected", "withdrawn", "archived"],
    screening: ["interview", "offer", "rejected", "withdrawn", "archived"],
    interview: ["interview", "offer", "rejected", "withdrawn", "archived"],
    offer: ["accepted", "rejected", "withdrawn", "archived"],
    accepted: ["archived"],
    rejected: ["archived"],
    withdrawn: ["archived"],
    archived: [],
};

export const BOARD_STAGES = ["saved", "preparing", "applied", "screening", "interview", "offer", "accepted"];
