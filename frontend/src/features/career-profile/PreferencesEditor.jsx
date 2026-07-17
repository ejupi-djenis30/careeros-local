const splitList = (value) => value.split(",").map((item) => item.trim()).filter(Boolean);

function NumberField({ label, value, onChange, ...props }) {
    return <label className="field-stack"><span>{label}</span><input className="form-control" type="number" value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} {...props} /></label>;
}

export function PreferencesEditor({ preferences, onChange }) {
    const update = (field, value) => onChange({ ...preferences, [field]: value });
    return (
        <section className="surface-section" aria-labelledby="preferences-title">
            <div className="section-heading"><div><span className="section-kicker">Vincoli personali</span><h2 id="preferences-title">Preferenze</h2></div><span className="section-number">03</span></div>
            <div className="form-grid form-grid--3">
                <NumberField label="Carico minimo %" min="0" max="100" value={preferences.workload_min} onChange={(value) => update("workload_min", value)} />
                <NumberField label="Carico massimo %" min="0" max="100" value={preferences.workload_max} onChange={(value) => update("workload_max", value)} />
                <NumberField label="Salario minimo CHF" min="0" step="1000" value={preferences.salary_min_chf} onChange={(value) => update("salary_min_chf", value)} />
                <label className="field-stack"><span>Lingue preferite</span><input className="form-control" value={(preferences.preferred_languages || []).join(", ")} onChange={(e) => update("preferred_languages", splitList(e.target.value))} placeholder="it, de, en" /></label>
                <NumberField label="Distanza massima km" min="0" value={preferences.hard_max_distance_km} onChange={(value) => update("hard_max_distance_km", value)} />
                <label className="check-line check-line--field"><input type="checkbox" checked={Boolean(preferences.remote_only)} onChange={(e) => update("remote_only", e.target.checked)} /> Solo ruoli da remoto</label>
            </div>
        </section>
    );
}

