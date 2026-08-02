const numberChange = (provider, setProvider, key, value) => setProvider({ ...provider, request: { ...provider.request, [key]: Number(value) } });

export function ProviderAdvanced({ provider, setProvider, advanced, setAdvanced, t }) {
    return (
        <details className="provider-advanced">
            <summary>{t("providers.advanced")}</summary>
            <div className="form-grid form-grid--4">
                <label className="field-stack"><span>{t("providers.method")}</span><select className="form-select" value={provider.request.method} onChange={(event) => setProvider({ ...provider, request: { ...provider.request, method: event.target.value } })}><option value="GET">{t("providers.methodGet")}</option><option value="POST">{t("providers.methodPost")}</option></select></label>
                {["timeout_seconds", "max_response_bytes", "max_pages", "page_size", "throttle_ms", "retries"].map((key) => <label className="field-stack" key={key}><span>{t(`providers.${key}`)}</span><input className="form-control" type="number" min="0" value={provider.request[key]} onChange={(event) => numberChange(provider, setProvider, key, event.target.value)} /></label>)}
            </div>
            <div className="form-grid form-grid--2">
                <label className="field-stack"><span>{t("providers.queryParams")}</span><textarea className="form-control provider-json" value={advanced.queryParams} onChange={(event) => setAdvanced({ ...advanced, queryParams: event.target.value })} spellCheck="false" /></label>
                <label className="field-stack"><span>{t("providers.headers")}</span><textarea className="form-control provider-json" value={advanced.headers} onChange={(event) => setAdvanced({ ...advanced, headers: event.target.value })} spellCheck="false" /><small>{t("providers.headersCopy")}</small></label>
                {provider.request.method === "POST" && <label className="field-stack"><span>{t("providers.jsonBody")}</span><textarea className="form-control provider-json" value={advanced.jsonBody} onChange={(event) => setAdvanced({ ...advanced, jsonBody: event.target.value })} spellCheck="false" /></label>}
                <label className="field-stack"><span>{t("providers.domains")}</span><input className="form-control" value={(provider.capabilities.accepted_domains || []).join(", ")} onChange={(event) => setProvider({ ...provider, capabilities: { ...provider.capabilities, accepted_domains: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) } })} /></label>
                <label className="field-stack"><span>{t("providers.languages")}</span><input className="form-control" value={(provider.capabilities.supported_languages || []).join(", ")} onChange={(event) => setProvider({ ...provider, capabilities: { ...provider.capabilities, supported_languages: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) } })} /></label>
            </div>
        </details>
    );
}
