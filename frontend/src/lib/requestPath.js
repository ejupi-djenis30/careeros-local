const VALIDATION_ORIGIN = "https://careeros.invalid";
const API_PATH = "/api/v1";

function hasControlCharacters(value) {
    return Array.from(value).some((character) => {
        const code = character.codePointAt(0);
        return code < 0x20 || code === 0x7f;
    });
}

export function validateRequestPath(value) {
    if (
        typeof value !== "string"
        || !value.startsWith("/")
        || value.startsWith("//")
        || value.includes("\\")
        || value.includes("#")
        || value.includes(" ")
        || hasControlCharacters(value)
    ) {
        throw new TypeError("API request path must be a canonical absolute path.");
    }

    const pathname = value.split("?", 1)[0];
    for (const segment of pathname.split("/")) {
        let decoded;
        try {
            decoded = decodeURIComponent(segment);
        } catch {
            throw new TypeError("API request path must use valid URL encoding.");
        }
        if (
            decoded === "."
            || decoded === ".."
            || decoded.includes("/")
            || decoded.includes("\\")
            || hasControlCharacters(decoded)
        ) {
            throw new TypeError("API request path must not contain traversal or encoded separators.");
        }
    }

    const target = new URL(`${API_PATH}${value}`, VALIDATION_ORIGIN);
    if (
        target.origin !== VALIDATION_ORIGIN
        || target.pathname !== `${API_PATH}${pathname}`
        || !target.pathname.startsWith(`${API_PATH}/`)
    ) {
        throw new TypeError("API request path must remain inside the configured API boundary.");
    }
    return value;
}
