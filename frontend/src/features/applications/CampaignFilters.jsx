import { useI18n } from "../../i18n/useI18n";
import { STAGES, getStageLabels } from "./applicationModel";

const PRIORITIES = ["Urgent", "High", "Medium", "Low"];

const PRIORITY_KEYS = {
    Urgent: "campaign.priorityUrgent",
    High: "campaign.priorityHigh",
    Medium: "campaign.priorityMedium",
    Low: "campaign.priorityLow",
};

export function CampaignFilters({ campaigns = [], filters = {}, onChange }) {
    const { t } = useI18n();
    const stageLabels = getStageLabels(t);

    const update = (key, value) => {
        onChange?.({ ...filters, [key]: value });
    };

    return (
        <div className="campaign-filters">
            <div className="form-grid form-grid--4">
                <label className="field-stack">
                    <span>{t("campaign.filterQuery")}</span>
                    <input
                        className="form-control"
                        type="search"
                        maxLength="200"
                        value={filters.query || ""}
                        onChange={(e) => update("query", e.target.value)}
                    />
                </label>
                <label className="field-stack">
                    <span>{t("campaign.filterCampaign")}</span>
                    <select
                        className="form-select"
                        value={filters.campaignId || ""}
                        onChange={(e) => update("campaignId", e.target.value)}
                    >
                        <option value="">{t("campaign.filterCampaignAll")}</option>
                        {campaigns.map((c) => (
                            <option key={c.id} value={c.id}>
                                {c.name}
                            </option>
                        ))}
                    </select>
                </label>
                <label className="field-stack">
                    <span>{t("campaign.filterStage")}</span>
                    <select
                        className="form-select"
                        value={filters.stage || ""}
                        onChange={(e) => update("stage", e.target.value)}
                    >
                        <option value="">{t("campaign.filterStageAll")}</option>
                        {STAGES.map((s) => (
                            <option key={s} value={s}>
                                {stageLabels[s]}
                            </option>
                        ))}
                    </select>
                </label>
                <label className="field-stack">
                    <span>{t("campaign.filterPriority")}</span>
                    <select
                        className="form-select"
                        value={filters.priority || ""}
                        onChange={(e) => update("priority", e.target.value)}
                    >
                        <option value="">{t("campaign.filterPriorityAll")}</option>
                        {PRIORITIES.map((p) => (
                            <option key={p} value={p}>
                                {t(PRIORITY_KEYS[p])}
                            </option>
                        ))}
                    </select>
                </label>
            </div>
        </div>
    );
}
