import { useI18n } from "../../../i18n/useI18n";

const splitList = (value) => value.split(",").map((item) => item.trim()).filter(Boolean);

function ListField({ label, value, onChange, placeholder }) {
    return <label className="field-stack"><span>{label}</span><input className="form-control" value={(value || []).join(", ")} onChange={(event) => onChange(splitList(event.target.value))} placeholder={placeholder} /></label>;
}

function NumberField({ label, value, onChange, ...props }) {
    return <label className="field-stack"><span>{label}</span><input className="form-control" type="number" value={value ?? ""} onChange={(event) => onChange(event.target.value === "" ? null : Number(event.target.value))} {...props} /></label>;
}

export function GoalDetails({ payload, onChange }) {
    const { t } = useI18n();
    const update = (field, value) => onChange({ ...payload, [field]: value });
    const compensation = payload.compensation || { currency: "CHF", minimum: null, maximum: null, period: "year" };
    const updateCompensation = (field, value) => update("compensation", { ...compensation, [field]: value });
    return (
        <div className="goal-details">
            <div className="form-grid form-grid--3">
                <label className="field-stack"><span>{t("goal.status")}</span><select className="form-select" value={payload.status || "active"} onChange={(event) => onChange({ ...payload, status: event.target.value, progress_percent: event.target.value === "achieved" ? 100 : payload.progress_percent })}>{["draft", "active", "paused", "achieved", "abandoned"].map((status) => <option key={status} value={status}>{t(`goal.status.${status}`)}</option>)}</select></label>
                <NumberField label={t("goal.priority")} min="1" max="5" value={payload.priority ?? 3} onChange={(value) => update("priority", value)} />
                <NumberField label={t("goal.progress")} min="0" max="100" value={payload.progress_percent ?? 0} onChange={(value) => update("progress_percent", value)} />
                <label className="field-stack"><span>{t("goal.startDate")}</span><input className="form-control" type="date" value={payload.start_date || ""} onChange={(event) => update("start_date", event.target.value)} /></label>
                <label className="field-stack"><span>{t("goal.targetDate")}</span><input className="form-control" type="date" value={payload.target_date || ""} onChange={(event) => update("target_date", event.target.value)} /></label>
            </div>
            <label className="field-stack"><span>{t("goal.rationale")}</span><textarea className="form-control" rows="3" maxLength="5000" value={payload.rationale || ""} onChange={(event) => update("rationale", event.target.value)} placeholder={t("goal.rationalePlaceholder")} /></label>
            <div className="form-grid form-grid--3">
                <ListField label={t("goal.targetRoles")} value={payload.target_roles} onChange={(value) => update("target_roles", value)} placeholder={t("goal.rolesPlaceholder")} />
                <ListField label={t("goal.targetIndustries")} value={payload.target_industries} onChange={(value) => update("target_industries", value)} placeholder={t("goal.industriesPlaceholder")} />
                <ListField label={t("goal.targetLocations")} value={payload.target_locations} onChange={(value) => update("target_locations", value)} placeholder={t("goal.locationsPlaceholder")} />
                <ListField label={t("goal.targetSeniority")} value={payload.target_seniority} onChange={(value) => update("target_seniority", value)} placeholder={t("goal.seniorityPlaceholder")} />
                <ListField label={t("goal.workModes")} value={payload.work_modes} onChange={(value) => update("work_modes", value)} placeholder={t("goal.workModesPlaceholder")} />
                <ListField label={t("goal.contractTypes")} value={payload.contract_types} onChange={(value) => update("contract_types", value)} placeholder={t("goal.contractTypesPlaceholder")} />
            </div>
            <fieldset className="goal-subsection"><legend>{t("goal.compensation")}</legend><div className="form-grid form-grid--4"><label className="field-stack"><span>{t("goal.currency")}</span><input className="form-control" maxLength="3" value={compensation.currency || "CHF"} onChange={(event) => updateCompensation("currency", event.target.value.toUpperCase())} /></label><NumberField label={t("goal.compensationMin")} min="0" value={compensation.minimum} onChange={(value) => updateCompensation("minimum", value)} /><NumberField label={t("goal.compensationMax")} min="0" value={compensation.maximum} onChange={(value) => updateCompensation("maximum", value)} /><label className="field-stack"><span>{t("goal.period")}</span><select className="form-select" value={compensation.period || "year"} onChange={(event) => updateCompensation("period", event.target.value)}>{["hour", "day", "month", "year"].map((period) => <option key={period} value={period}>{t(`preferences.period.${period}`)}</option>)}</select></label></div></fieldset>
            <div className="form-grid form-grid--3"><ListField label={t("goal.successCriteria")} value={payload.success_criteria} onChange={(value) => update("success_criteria", value)} placeholder={t("goal.successPlaceholder")} /><ListField label={t("goal.mustHaves")} value={payload.must_haves} onChange={(value) => update("must_haves", value)} /><ListField label={t("goal.dealBreakers")} value={payload.deal_breakers} onChange={(value) => update("deal_breakers", value)} /></div>
        </div>
    );
}
