import { useI18n } from "../../i18n/useI18n";

const splitList = (value) => value.split(",").map((item) => item.trim()).filter(Boolean);

function NumberField({ label, value, onChange, ...props }) {
    return <label className="field-stack"><span>{label}</span><input className="form-control" type="number" value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} {...props} /></label>;
}

function ListField({ label, value, onChange, placeholder }) {
    return <label className="field-stack"><span>{label}</span><input className="form-control" value={(value || []).join(", ")} onChange={(event) => onChange(splitList(event.target.value))} placeholder={placeholder} /></label>;
}

export function PreferencesEditor({ preferences, jobSources = [], onChange }) {
    const { t } = useI18n();
    const update = (field, value) => onChange({ ...preferences, [field]: value });
    const salary = preferences.salary || { currency: "CHF", minimum: preferences.salary_min_chf ?? null, maximum: null, period: "year" };
    const updateSalary = (field, value) => update("salary", { ...salary, [field]: value });
    const toggleWorkMode = (mode, enabled) => update("preferred_work_modes", enabled
        ? [...new Set([...(preferences.preferred_work_modes || []), mode])]
        : (preferences.preferred_work_modes || []).filter((item) => item !== mode));
    const toggleJobSource = (source, enabled) => update("job_source_consents", {
        ...(preferences.job_source_consents || {}),
        [source]: enabled,
    });
    return (
        <section className="surface-section" aria-labelledby="preferences-title">
            <div className="section-heading"><div><span className="section-kicker">{t("preferences.kicker")}</span><h2 id="preferences-title">{t("preferences.title")}</h2></div><span className="section-number">03</span></div>
            <div className="form-grid form-grid--3">
                <ListField label={t("preferences.roles")} value={preferences.target_roles} onChange={(value) => update("target_roles", value)} placeholder="Staff Engineer, Engineering Manager" />
                <ListField label={t("preferences.industries")} value={preferences.target_industries} onChange={(value) => update("target_industries", value)} placeholder="Software, healthcare" />
                <ListField label={t("preferences.locations")} value={preferences.preferred_locations} onChange={(value) => update("preferred_locations", value)} placeholder="Zurich, Switzerland" />
                <NumberField label={t("preferences.workloadMin")} min="0" max="100" value={preferences.workload_min} onChange={(value) => update("workload_min", value)} />
                <NumberField label={t("preferences.workloadMax")} min="0" max="100" value={preferences.workload_max} onChange={(value) => update("workload_max", value)} />
                <label className="field-stack"><span>{t("preferences.languages")}</span><input className="form-control" value={(preferences.preferred_languages || []).join(", ")} onChange={(e) => update("preferred_languages", splitList(e.target.value))} placeholder="en, de, fr" /></label>
                <NumberField label={t("preferences.distance")} min="0" value={preferences.hard_max_distance_km} onChange={(value) => update("hard_max_distance_km", value)} />
                <label className="field-stack"><span>{t("preferences.availableFrom")}</span><input className="form-control" type="date" value={preferences.available_from || ""} onChange={(event) => update("available_from", event.target.value)} /></label>
                <NumberField label={t("preferences.notice")} min="0" max="730" value={preferences.notice_period_days} onChange={(value) => update("notice_period_days", value)} />
                <NumberField label={t("preferences.travel")} min="0" max="100" value={preferences.travel_max_percent} onChange={(value) => update("travel_max_percent", value)} />
                <label className="field-stack"><span>{t("preferences.relocation")}</span><select className="form-select" value={preferences.relocation || "no"} onChange={(event) => update("relocation", event.target.value)}><option value="no">{t("preferences.relocation.no")}</option><option value="within_country">{t("preferences.relocation.country")}</option><option value="international">{t("preferences.relocation.international")}</option><option value="open">{t("preferences.relocation.open")}</option></select></label>
            </div>
            <fieldset className="goal-subsection"><legend>{t("preferences.workModes")}</legend><div className="preference-checks">{["onsite", "hybrid", "remote"].map((value) => <label className="check-line" key={value}><input type="checkbox" checked={(preferences.preferred_work_modes || []).includes(value)} onChange={(event) => toggleWorkMode(value, event.target.checked)} /> {t(`preferences.${value}`)}</label>)}<label className="check-line"><input type="checkbox" checked={Boolean(preferences.remote_only)} onChange={(event) => onChange({ ...preferences, remote_only: event.target.checked, preferred_work_modes: event.target.checked ? ["remote"] : (preferences.preferred_work_modes || []) })} /> {t("preferences.remoteOnly")}</label></div></fieldset>
            <fieldset className="goal-subsection"><legend>{t("preferences.sources")}</legend><p className="section-intro">{t("preferences.sourcesCopy")}</p><div className="preference-checks">{jobSources.filter((source) => source.network).map((source) => { const stored = preferences.job_source_consents?.[source.key]; const checked = typeof stored === "boolean" ? stored : source.consented; return <label className="check-line" key={source.key}><input type="checkbox" checked={Boolean(checked)} disabled={!source.available} onChange={(event) => toggleJobSource(source.key, event.target.checked)} /> <span><strong>{source.label}</strong> · {source.available ? source.description : t("preferences.unavailable")}</span></label>; })}</div></fieldset>
            <fieldset className="goal-subsection"><legend>{t("preferences.compensation")}</legend><div className="form-grid form-grid--4"><label className="field-stack"><span>{t("preferences.currency")}</span><input className="form-control" maxLength="3" value={salary.currency || "CHF"} onChange={(event) => updateSalary("currency", event.target.value.toUpperCase())} /></label><NumberField label={t("preferences.salaryMin")} min="0" step="1000" value={salary.minimum} onChange={(value) => updateSalary("minimum", value)} /><NumberField label={t("preferences.salaryMax")} min="0" step="1000" value={salary.maximum} onChange={(value) => updateSalary("maximum", value)} /><label className="field-stack"><span>{t("preferences.salaryPeriod")}</span><select className="form-select" value={salary.period || "year"} onChange={(event) => updateSalary("period", event.target.value)}>{["hour", "day", "month", "year"].map((period) => <option key={period} value={period}>{t(`preferences.period.${period}`)}</option>)}</select></label></div></fieldset>
            <div className="form-grid form-grid--2"><ListField label={t("preferences.values")} value={preferences.company_values} onChange={(value) => update("company_values", value)} placeholder="Autonomy, sustainability" /><ListField label={t("preferences.benefits")} value={preferences.desired_benefits} onChange={(value) => update("desired_benefits", value)} placeholder="Learning budget, pension" /><ListField label={t("preferences.excludedCompanies")} value={preferences.excluded_companies} onChange={(value) => update("excluded_companies", value)} /><ListField label={t("preferences.excludedIndustries")} value={preferences.excluded_industries} onChange={(value) => update("excluded_industries", value)} /></div>
        </section>
    );
}
