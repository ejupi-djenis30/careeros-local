function hasAsciiControlOrSpace(value) {
    return [...value].some((character) => {
        const codePoint = character.codePointAt(0);
        return codePoint <= 0x20 || codePoint === 0x7f;
    });
}

export function safeExternalUrl(value) {
    if (!value || typeof value !== "string") return null;
    try {
        const candidate = value.trim();
        if (!candidate || candidate.includes("\\") || hasAsciiControlOrSpace(candidate)) return null;
        const parsed = new URL(candidate);
        if (
            parsed.protocol !== "https:"
            || !parsed.hostname
            || parsed.username
            || parsed.password
        ) return null;
        return parsed.href;
    } catch {
        return null;
    }
}

export function safeMailto(value) {
    if (!value || typeof value !== "string") return null;
    const email = value.trim();
    if (email.length > 254 || hasAsciiControlOrSpace(email)) return null;
    const separator = email.indexOf("@");
    if (separator < 1 || separator !== email.lastIndexOf("@")) return null;
    const local = email.slice(0, separator);
    const domain = email.slice(separator + 1);
    if (
        local.length > 64
        || local.startsWith(".")
        || local.endsWith(".")
        || local.includes("..")
        || /["(),:;<>[\]\\]/u.test(local)
        || !domain
        || /[/?#:@\\]/u.test(domain)
    ) return null;

    try {
        const hostname = new URL(`https://${domain}/`).hostname;
        const labels = hostname.split(".");
        if (
            hostname.length > 253
            || labels.length < 2
            || labels.some((label) => (
                !/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/iu.test(label)
            ))
        ) return null;
        return `mailto:${encodeURIComponent(local)}@${hostname}`;
    } catch {
        return null;
    }
}
