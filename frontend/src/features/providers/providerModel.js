export const REDACTED_SECRET = "••••••••";
export const PRESERVE_SECRET = "__CAREEROS_PRESERVE_SECRET__";

const defaultFields = () => ({
    id: { source: "id", attribute: null, default: null },
    title: { source: "title", attribute: null, default: null },
    company: { source: "company", attribute: null, default: null },
    location: { source: "location", attribute: null, default: null },
    description: { source: "description", attribute: null, default: null },
    url: { source: "url", attribute: null, default: null },
});

export function emptyProvider() {
    return {
        key: "",
        display_name: "",
        description: "",
        adapter_kind: "json",
        enabled: false,
        request: {
            base_url: "https://",
            path_template: "/jobs",
            method: "GET",
            query_params: { q: "{query}", location: "{location}", page: "{page}", limit: "{page_size}" },
            json_body: null,
            headers: {},
            timeout_seconds: 20,
            max_response_bytes: 2_000_000,
            max_pages: 5,
            page_size: 50,
            throttle_ms: 250,
            retries: 1,
        },
        extraction: { items_path: "jobs", item_selector: null, total_path: "total", fields: defaultFields() },
        capabilities: { accepted_domains: ["*"], supported_languages: ["en"] },
    };
}

export function providerForEdit(provider) {
    return JSON.parse(JSON.stringify(provider || emptyProvider()));
}

export function switchAdapter(provider, adapter) {
    const next = providerForEdit(provider);
    next.adapter_kind = adapter;
    if (adapter === "html") {
        next.extraction.items_path = null;
        next.extraction.total_path = null;
        next.extraction.item_selector ||= ".job";
        next.extraction.fields = {
            id: { source: "a", attribute: "href", default: null },
            title: { source: ".title", attribute: null, default: null },
            company: { source: ".company", attribute: null, default: null },
            location: { source: ".location", attribute: null, default: null },
            description: { source: ".description", attribute: null, default: null },
            url: { source: "a", attribute: "href", default: null },
        };
    } else {
        next.extraction.items_path ||= "jobs";
        next.extraction.total_path ||= "total";
        next.extraction.item_selector = null;
        next.extraction.fields = defaultFields();
    }
    return next;
}

export function parseObject(value, label) {
    let parsed;
    try {
        parsed = value.trim() ? JSON.parse(value) : {};
    } catch {
        throw new Error(label);
    }
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error(label);
    return parsed;
}

export function payloadForSave(provider, advanced) {
    const headers = parseObject(advanced.headers, advanced.invalidJson);
    Object.entries(headers).forEach(([name, value]) => {
        if (value === REDACTED_SECRET) headers[name] = PRESERVE_SECRET;
    });
    return {
        key: provider.key,
        display_name: provider.display_name,
        description: provider.description,
        adapter_kind: provider.adapter_kind,
        enabled: provider.enabled,
        request: {
            ...provider.request,
            query_params: parseObject(advanced.queryParams, advanced.invalidJson),
            headers,
            json_body: provider.request.method === "POST"
                ? parseObject(advanced.jsonBody, advanced.invalidJson)
                : null,
        },
        extraction: provider.extraction,
        capabilities: provider.capabilities,
        ...(provider.id ? { expected_revision: provider.revision } : {}),
    };
}

export function advancedText(provider) {
    return {
        queryParams: JSON.stringify(provider.request.query_params || {}, null, 2),
        headers: JSON.stringify(provider.request.headers || {}, null, 2),
        jsonBody: JSON.stringify(provider.request.json_body || {}, null, 2),
    };
}
