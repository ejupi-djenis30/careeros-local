const splitList = (value) => value.split(",").map((item) => item.trim()).filter(Boolean);

function ListField({ label, value, onChange, placeholder }) {
    return <label className="field-stack"><span>{label}</span><input className="form-control" value={(value || []).join(", ")} onChange={(event) => onChange(splitList(event.target.value))} placeholder={placeholder} /></label>;
}

function NumberField({ label, value, onChange, ...props }) {
    return <label className="field-stack"><span>{label}</span><input className="form-control" type="number" value={value ?? ""} onChange={(event) => onChange(event.target.value === "" ? null : Number(event.target.value))} {...props} /></label>;
}

export function GoalDetails({ payload, onChange }) {
    const update = (field, value) => onChange({ ...payload, [field]: value });
    const compensation = payload.compensation || { currency: "CHF", minimum: null, maximum: null, period: "year" };
    const updateCompensation = (field, value) => update("compensation", { ...compensation, [field]: value });
    return (
        <div className="goal-details">
            <div className="form-grid form-grid--3">
                <label className="field-stack"><span>Stato obiettivo</span><select className="form-select" value={payload.status || "active"} onChange={(event) => update("status", event.target.value)}><option value="draft">Bozza</option><option value="active">Attivo</option><option value="paused">In pausa</option><option value="achieved">Raggiunto</option><option value="abandoned">Abbandonato</option></select></label>
                <NumberField label="Priorità" min="1" max="5" value={payload.priority ?? 3} onChange={(value) => update("priority", value)} />
                <label className="field-stack"><span>Data obiettivo</span><input className="form-control" type="date" value={payload.target_date || ""} onChange={(event) => update("target_date", event.target.value)} /></label>
            </div>
            <div className="form-grid form-grid--3">
                <ListField label="Ruoli target" value={payload.target_roles} onChange={(value) => update("target_roles", value)} placeholder="Staff Engineer, Engineering Manager" />
                <ListField label="Settori target" value={payload.target_industries} onChange={(value) => update("target_industries", value)} placeholder="Software, Fintech" />
                <ListField label="Località target" value={payload.target_locations} onChange={(value) => update("target_locations", value)} placeholder="Zurigo, remoto" />
                <ListField label="Seniorità target" value={payload.target_seniority} onChange={(value) => update("target_seniority", value)} placeholder="senior, staff, lead" />
                <ListField label="Modalità" value={payload.work_modes} onChange={(value) => update("work_modes", value)} placeholder="onsite, hybrid, remote" />
                <ListField label="Tipi di contratto" value={payload.contract_types} onChange={(value) => update("contract_types", value)} placeholder="permanent, contract" />
            </div>
            <fieldset className="goal-subsection"><legend>Compenso desiderato</legend><div className="form-grid form-grid--4"><label className="field-stack"><span>Valuta</span><input className="form-control" maxLength="3" value={compensation.currency || "CHF"} onChange={(event) => updateCompensation("currency", event.target.value.toUpperCase())} /></label><NumberField label="Compenso minimo" min="0" value={compensation.minimum} onChange={(value) => updateCompensation("minimum", value)} /><NumberField label="Compenso massimo" min="0" value={compensation.maximum} onChange={(value) => updateCompensation("maximum", value)} /><label className="field-stack"><span>Periodo</span><select className="form-select" value={compensation.period || "year"} onChange={(event) => updateCompensation("period", event.target.value)}><option value="hour">Ora</option><option value="day">Giorno</option><option value="month">Mese</option><option value="year">Anno</option></select></label></div></fieldset>
            <div className="form-grid form-grid--2"><ListField label="Requisiti irrinunciabili" value={payload.must_haves} onChange={(value) => update("must_haves", value)} /><ListField label="Deal breaker" value={payload.deal_breakers} onChange={(value) => update("deal_breakers", value)} /></div>
        </div>
    );
}
