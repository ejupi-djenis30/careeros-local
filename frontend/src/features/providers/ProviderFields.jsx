const FIELD_NAMES = ["id", "title", "company", "location", "description", "url", "application_url", "application_email", "posted_at", "workload_min", "workload_max", "country_code"];

export function ProviderFields({ provider, setProvider, t }) {
    const fields = provider.extraction.fields || {};
    const updateField = (name, key, value) => {
        const next = { ...fields };
        if (!value && !["id", "title"].includes(name) && key === "source") delete next[name];
        else next[name] = { source: "", attribute: null, default: null, ...next[name], [key]: value || null };
        setProvider({ ...provider, extraction: { ...provider.extraction, fields: next } });
    };
    return (
        <fieldset className="provider-fields">
            <legend>{t("providers.fields")}</legend>
            <p>{t(provider.adapter_kind === "json" ? "providers.fieldsJsonCopy" : "providers.fieldsHtmlCopy")}</p>
            <div className="provider-fields__grid">
                {FIELD_NAMES.map((name) => (
                    <div className="provider-field-row" key={name}>
                        <label><span>{t(`providers.field.${name}`)}{["id", "title"].includes(name) ? " *" : ""}</span><input className="form-control" value={fields[name]?.source || ""} onChange={(event) => updateField(name, "source", event.target.value)} required={["id", "title"].includes(name)} /></label>
                        {provider.adapter_kind === "html" && <label><span>{t("providers.attribute")}</span><input className="form-control" value={fields[name]?.attribute || ""} onChange={(event) => updateField(name, "attribute", event.target.value)} placeholder={t("providers.attributePlaceholder")} /></label>}
                    </div>
                ))}
            </div>
        </fieldset>
    );
}
