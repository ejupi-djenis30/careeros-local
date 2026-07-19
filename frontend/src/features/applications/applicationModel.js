export const STAGES = ["saved", "preparing", "applied", "screening", "interview", "offer", "accepted", "rejected", "withdrawn", "archived"];

export const STAGE_LABELS = {
    saved: "Saved",
    preparing: "Preparing",
    applied: "Applied",
    screening: "Screening",
    interview: "Interview",
    offer: "Offer",
    accepted: "Accepted",
    rejected: "Rejected",
    withdrawn: "Withdrawn",
    archived: "Archived",
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
