const splitList = (value) => value.split(",").map((item) => item.trim()).filter(Boolean);

function NumberField({ label, value, onChange, ...props }) {
    return <label className="field-stack"><span>{label}</span><input className="form-control" type="number" value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} {...props} /></label>;
}

function ListField({ label, value, onChange, placeholder }) {
    return <label className="field-stack"><span>{label}</span><input className="form-control" value={(value || []).join(", ")} onChange={(event) => onChange(splitList(event.target.value))} placeholder={placeholder} /></label>;
}

export function PreferencesEditor({ preferences, jobSources = [], onChange }) {
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
            <div className="section-heading"><div><span className="section-kicker">Vincoli personali</span><h2 id="preferences-title">Preferenze</h2></div><span className="section-number">03</span></div>
            <div className="form-grid form-grid--3">
                <ListField label="Ruoli preferiti" value={preferences.target_roles} onChange={(value) => update("target_roles", value)} placeholder="Staff Engineer, Engineering Manager" />
                <ListField label="Settori preferiti" value={preferences.target_industries} onChange={(value) => update("target_industries", value)} placeholder="Software, salute" />
                <ListField label="Località preferite" value={preferences.preferred_locations} onChange={(value) => update("preferred_locations", value)} placeholder="Zurigo, Svizzera" />
                <NumberField label="Carico minimo %" min="0" max="100" value={preferences.workload_min} onChange={(value) => update("workload_min", value)} />
                <NumberField label="Carico massimo %" min="0" max="100" value={preferences.workload_max} onChange={(value) => update("workload_max", value)} />
                <label className="field-stack"><span>Lingue preferite</span><input className="form-control" value={(preferences.preferred_languages || []).join(", ")} onChange={(e) => update("preferred_languages", splitList(e.target.value))} placeholder="it, de, en" /></label>
                <NumberField label="Distanza massima km" min="0" value={preferences.hard_max_distance_km} onChange={(value) => update("hard_max_distance_km", value)} />
                <label className="field-stack"><span>Disponibile dal</span><input className="form-control" type="date" value={preferences.available_from || ""} onChange={(event) => update("available_from", event.target.value)} /></label>
                <NumberField label="Preavviso (giorni)" min="0" max="730" value={preferences.notice_period_days} onChange={(value) => update("notice_period_days", value)} />
                <NumberField label="Trasferte massime %" min="0" max="100" value={preferences.travel_max_percent} onChange={(value) => update("travel_max_percent", value)} />
                <label className="field-stack"><span>Disponibilità al trasferimento</span><select className="form-select" value={preferences.relocation || "no"} onChange={(event) => update("relocation", event.target.value)}><option value="no">No</option><option value="within_country">Nel paese</option><option value="international">Internazionale</option><option value="open">Da valutare</option></select></label>
            </div>
            <fieldset className="goal-subsection"><legend>Modalità di lavoro</legend><div className="preference-checks">{[["onsite", "In sede"], ["hybrid", "Ibrido"], ["remote", "Remoto"]].map(([value, label]) => <label className="check-line" key={value}><input type="checkbox" checked={(preferences.preferred_work_modes || []).includes(value)} onChange={(event) => toggleWorkMode(value, event.target.checked)} /> {label}</label>)}<label className="check-line"><input type="checkbox" checked={Boolean(preferences.remote_only)} onChange={(event) => onChange({ ...preferences, remote_only: event.target.checked, preferred_work_modes: event.target.checked ? ["remote"] : (preferences.preferred_work_modes || []) })} /> Solo ruoli da remoto</label></div></fieldset>
            <fieldset className="goal-subsection"><legend>Sorgenti lavoro e accesso rete</legend><p className="section-intro">L’archivio locale è sempre disponibile. Ogni sorgente online resta bloccata finché non la abiliti esplicitamente.</p><div className="preference-checks">{jobSources.filter((source) => source.network).map((source) => { const stored = preferences.job_source_consents?.[source.key]; const checked = typeof stored === "boolean" ? stored : source.consented; return <label className="check-line" key={source.key}><input type="checkbox" checked={Boolean(checked)} disabled={!source.available} onChange={(event) => toggleJobSource(source.key, event.target.checked)} /> <span><strong>{source.label}</strong> · {source.available ? source.description : "non disponibile in questa build"}</span></label>; })}</div></fieldset>
            <fieldset className="goal-subsection"><legend>Compenso desiderato</legend><div className="form-grid form-grid--4"><label className="field-stack"><span>Valuta</span><input className="form-control" maxLength="3" value={salary.currency || "CHF"} onChange={(event) => updateSalary("currency", event.target.value.toUpperCase())} /></label><NumberField label="Salario minimo" min="0" step="1000" value={salary.minimum} onChange={(value) => updateSalary("minimum", value)} /><NumberField label="Salario massimo" min="0" step="1000" value={salary.maximum} onChange={(value) => updateSalary("maximum", value)} /><label className="field-stack"><span>Periodo salariale</span><select className="form-select" value={salary.period || "year"} onChange={(event) => updateSalary("period", event.target.value)}><option value="hour">Ora</option><option value="day">Giorno</option><option value="month">Mese</option><option value="year">Anno</option></select></label></div></fieldset>
            <div className="form-grid form-grid--2"><ListField label="Valori aziendali" value={preferences.company_values} onChange={(value) => update("company_values", value)} placeholder="Autonomia, sostenibilità" /><ListField label="Benefit desiderati" value={preferences.desired_benefits} onChange={(value) => update("desired_benefits", value)} placeholder="Formazione, previdenza" /><ListField label="Aziende escluse" value={preferences.excluded_companies} onChange={(value) => update("excluded_companies", value)} /><ListField label="Settori esclusi" value={preferences.excluded_industries} onChange={(value) => update("excluded_industries", value)} /></div>
        </section>
    );
}
