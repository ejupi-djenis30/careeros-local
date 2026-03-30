/**
 * Returns true only if url uses http: or https: scheme.
 * Prevents javascript: and data: URLs from being used in href attributes (XSS).
 */
export function isSafeUrl(url) {
    if (!url || typeof url !== 'string') return false;
    try {
        const parsed = new URL(url);
        return parsed.protocol === 'http:' || parsed.protocol === 'https:';
    } catch {
        return false;
    }
}

/**
 * Returns url if it passes the protocol-safety check, otherwise null.
 */
export function safeUrl(url) {
    return isSafeUrl(url) ? url : null;
}
