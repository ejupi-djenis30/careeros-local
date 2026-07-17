function Field({ label, children, hint }) {
    return (
        <label className="field-stack">
            <span>{label}</span>
            {children}
            {hint && <small>{hint}</small>}
        </label>
    );
}

export function IdentityEditor({ profile, onChange }) {
    const update = (field, value) => onChange({ ...profile, [field]: value });
    const locationName = profile.location?.name || profile.location?.city || "";

    return (
        <section className="surface-section" aria-labelledby="identity-title">
            <div className="section-heading">
                <div><span className="section-kicker">Identità professionale</span><h2 id="identity-title">Chi sei e cosa porti</h2></div>
                <span className="section-number">01</span>
            </div>
            <div className="form-grid form-grid--2">
                <Field label="Nome visualizzato"><input className="form-control" value={profile.display_name} onChange={(e) => update("display_name", e.target.value)} required maxLength={160} /></Field>
                <Field label="Titolo professionale"><input className="form-control" value={profile.headline} onChange={(e) => update("headline", e.target.value)} placeholder="Es. Product designer · sistemi complessi" maxLength={240} /></Field>
                <Field label="Email"><input className="form-control" type="email" value={profile.email} onChange={(e) => update("email", e.target.value)} autoComplete="email" /></Field>
                <Field label="Telefono"><input className="form-control" value={profile.phone} onChange={(e) => update("phone", e.target.value)} autoComplete="tel" /></Field>
                <Field label="Località" hint="Testo libero: non viene chiamato alcun servizio di mappe."><input className="form-control" value={locationName} onChange={(e) => update("location", { ...profile.location, name: e.target.value })} placeholder="Zurigo, CH" /></Field>
                <Field label="Nazionalità"><input className="form-control" value={profile.nationality} onChange={(e) => update("nationality", e.target.value)} /></Field>
                <Field label="Data di nascita"><input className="form-control" type="date" value={profile.birth_date} onChange={(e) => update("birth_date", e.target.value)} /></Field>
                <Field label="Autorizzazioni di lavoro" hint="Separate da virgola"><input className="form-control" value={(profile.work_authorization || []).join(", ")} onChange={(e) => update("work_authorization", e.target.value.split(",").map((item) => item.trim()).filter(Boolean))} placeholder="CH, EU" /></Field>
            </div>
            <Field label="Profilo / sintesi"><textarea className="form-control" rows="6" value={profile.summary} onChange={(e) => update("summary", e.target.value)} placeholder="Una sintesi concreta: specializzazione, contesto, risultati e direzione." maxLength={20000} /></Field>
            <div className="form-grid form-grid--3">
                <Field label="Sito"><input className="form-control" type="url" value={profile.website} onChange={(e) => update("website", e.target.value)} placeholder="https://" /></Field>
                <Field label="LinkedIn"><input className="form-control" type="url" value={profile.linkedin} onChange={(e) => update("linkedin", e.target.value)} placeholder="https://" /></Field>
                <Field label="GitHub"><input className="form-control" type="url" value={profile.github} onChange={(e) => update("github", e.target.value)} placeholder="https://" /></Field>
            </div>
        </section>
    );
}

