export function brandAssetUrl(baseUrl = "/") {
    const normalizedBase = baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`;
    return `${normalizedBase}careeros.svg`;
}

export const CAREEROS_MARK_URL = brandAssetUrl(import.meta.env.BASE_URL || "/");
