const EXTERNAL_PROTOCOLS = new Set(["http:", "https:"]);

export function safeExternalUrl(value) {
    if (!value || typeof value !== "string") return null;
    try {
        const candidate = value.trim();
        const parsed = new URL(candidate);
        if (!EXTERNAL_PROTOCOLS.has(parsed.protocol) || parsed.username || parsed.password) return null;
        return candidate;
    } catch {
        return null;
    }
}

export function safeMailto(value) {
    if (!value || typeof value !== "string") return null;
    const email = value.trim();
    if (email.includes("\r") || email.includes("\n") || !email.includes("@")) return null;
    return `mailto:${encodeURIComponent(email).replace(/%40/gi, "@")}`;
}
