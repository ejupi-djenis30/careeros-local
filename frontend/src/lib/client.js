import { CAREEROS_API_ERROR_EVENT, CAREEROS_UNAUTHORIZED_EVENT } from "./events";

const DEFAULT_API_BASE = "/api/v1";
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);

function validateApiBase(candidate) {
    const value = (candidate || DEFAULT_API_BASE).trim().replace(/\/$/, "");
    if (value.startsWith("/")) return value;

    const parsed = new URL(value);
    if (!LOOPBACK_HOSTS.has(parsed.hostname)) {
        throw new Error("VITE_API_URL must be same-origin or point to a loopback host");
    }
    if (!["http:", "https:"].includes(parsed.protocol)) {
        throw new Error("VITE_API_URL must use HTTP(S)");
    }
    return parsed.toString().replace(/\/$/, "");
}

const INITIAL_API_BASE = validateApiBase(import.meta.env.VITE_API_URL);
let apiRuntime = Object.freeze({ apiBase: INITIAL_API_BASE, sessionToken: null });

// Kept as the browser-mode default for compatibility. Runtime requests use getApiBase().
export const API_BASE = INITIAL_API_BASE;

export function getApiBase() {
    return apiRuntime.apiBase;
}

export function configureApiRuntime({ apiBaseUrl, sessionToken }) {
    const apiBase = validateApiBase(apiBaseUrl);
    if (apiBase.startsWith("/")) {
        throw new Error("Desktop API URL must be an absolute loopback URL");
    }
    const token = String(sessionToken || "").trim();
    if (token.length < 43 || token.length > 128 || !/^[A-Za-z0-9_-]+$/.test(token)) {
        throw new Error("Desktop session token is invalid");
    }
    apiRuntime = Object.freeze({ apiBase, sessionToken: token });
    return apiRuntime;
}

export function resetApiRuntime() {
    apiRuntime = Object.freeze({ apiBase: INITIAL_API_BASE, sessionToken: null });
    ApiClient.accessToken = null;
    ApiClient._refreshPromise = null;
}

export class ApiError extends Error {
    constructor(message, { status = 0, details = null } = {}) {
        super(message);
        this.name = "ApiError";
        this.status = status;
        this.details = details;
    }
}

export class ApiClient {
    static accessToken = null;
    static _refreshPromise = null;
    static _suppressUnauthorized = false;

    static _dispatchApiError(message) {
        window.dispatchEvent(new CustomEvent(CAREEROS_API_ERROR_EVENT, { detail: { message } }));
    }

    static _extractErrorMessage(errorData, fallbackMessage) {
        if (typeof errorData?.detail === "string") return errorData.detail;
        if (Array.isArray(errorData?.detail)) {
            return errorData.detail.map((entry) => entry.msg || String(entry)).join(", ");
        }
        if (errorData?.detail && typeof errorData.detail === "object") {
            return errorData.detail.message || errorData.detail.code || fallbackMessage;
        }
        if (errorData?.detail) return JSON.stringify(errorData.detail);
        return errorData?.message || fallbackMessage;
    }

    static setToken(token) {
        this.accessToken = token || null;
    }

    static getToken() {
        return this.accessToken;
    }

    static getHeaders({ json = true } = {}) {
        const headers = {};
        if (json) headers["Content-Type"] = "application/json";
        if (this.getToken()) headers.Authorization = `Bearer ${this.getToken()}`;
        if (apiRuntime.sessionToken) headers["X-CareerOS-Session"] = apiRuntime.sessionToken;
        return headers;
    }

    static async _handleUnauthorized(originalUrl, originalConfig) {
        if (!this._refreshPromise) {
            this._refreshPromise = (async () => {
                const response = await fetch(`${getApiBase()}/auth/refresh`, {
                    method: "POST",
                    credentials: "include",
                    headers: this.getHeaders({ json: false }),
                });
                if (!response.ok) return null;
                const data = await response.json();
                if (!data.access_token) return null;
                this.setToken(data.access_token);
                return data.access_token;
            })();
        }

        let refreshedToken = null;
        try {
            refreshedToken = await this._refreshPromise;
        } catch {
            refreshedToken = null;
        } finally {
            this._refreshPromise = null;
        }

        if (refreshedToken) {
            return fetch(originalUrl, {
                ...originalConfig,
                headers: { ...originalConfig.headers, Authorization: `Bearer ${refreshedToken}` },
            });
        }

        window.dispatchEvent(new Event(CAREEROS_UNAUTHORIZED_EVENT));
        return null;
    }

    static async _parseError(response) {
        let data = {};
        try {
            const jsonResponse = typeof response.clone === "function" ? response.clone() : response;
            data = await jsonResponse.json();
        } catch {
            try {
                if (typeof response.text === "function") {
                    data = { detail: (await response.text()).slice(0, 300) };
                }
            } catch {
                data = {};
            }
        }
        return data;
    }

    static async request(endpoint, options = {}) {
        const url = `${getApiBase()}${endpoint}`;
        const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
        const controller = new AbortController();
        const timeoutMs = options.timeoutMs ?? 30_000;
        const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
        const callerSignal = options.signal;
        const abortFromCaller = () => controller.abort();
        callerSignal?.addEventListener("abort", abortFromCaller, { once: true });
        if (callerSignal?.aborted) controller.abort();

        const {
            signal: _ignoredSignal,
            timeoutMs: _ignoredTimeout,
            suppressGlobalError = false,
            responseType = "json",
            ...fetchOptions
        } = options;
        const config = {
            credentials: "include",
            ...fetchOptions,
            headers: {
                ...this.getHeaders({ json: !isFormData }),
                ...(options.headers || {}),
            },
            signal: controller.signal,
        };

        try {
            let response = await fetch(url, config);
            if (response.status === 401) {
                if (this._suppressUnauthorized) {
                    throw new ApiError("UNAUTHORIZED", { status: 401 });
                }
                response = await this._handleUnauthorized(url, config);
                if (!response) throw new ApiError("UNAUTHORIZED", { status: 401 });
            }

            if (!response.ok) {
                const details = await this._parseError(response);
                const message = this._extractErrorMessage(details, `Request failed (${response.status})`);
                if (!suppressGlobalError) this._dispatchApiError(message);
                throw new ApiError(message, { status: response.status, details });
            }

            if (response.status === 204) return null;
            if (responseType === "blob") {
                return {
                    blob: await response.blob(),
                    filename: this._filenameFromResponse(response),
                    sha256: response.headers.get("X-Content-SHA256"),
                };
            }
            return response.json();
        } catch (error) {
            if (error?.name === "AbortError") {
                throw new ApiError("The local service did not respond in time", { status: 0 });
            }
            throw error;
        } finally {
            clearTimeout(timeoutId);
            callerSignal?.removeEventListener("abort", abortFromCaller);
        }
    }

    static _filenameFromResponse(response) {
        const disposition = response.headers.get("Content-Disposition") || "";
        const utf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i);
        if (utf8) return this._safeFilename(decodeURIComponent(utf8[1]));
        const plain = disposition.match(/filename="?([^";]+)"?/i);
        return this._safeFilename(plain?.[1] || "download");
    }

    static _safeFilename(value) {
        const reserved = new Set(['\\', '/', ':', '*', '?', '"', '<', '>', '|']);
        const normalized = Array.from(String(value), (character) => {
            return character.charCodeAt(0) < 32 || reserved.has(character) ? "_" : character;
        }).join("").trim();
        return normalized.slice(0, 180) || "download";
    }

    static get(endpoint, signal, options = {}) {
        return this.request(endpoint, { method: "GET", signal, ...options });
    }

    static post(endpoint, body, options = {}) {
        return this.request(endpoint, { method: "POST", body: JSON.stringify(body), ...options });
    }

    static put(endpoint, body, options = {}) {
        return this.request(endpoint, { method: "PUT", body: JSON.stringify(body), ...options });
    }

    static patch(endpoint, body, options = {}) {
        return this.request(endpoint, { method: "PATCH", body: JSON.stringify(body), ...options });
    }

    static delete(endpoint, options = {}) {
        return this.request(endpoint, { method: "DELETE", ...options });
    }

    static postForm(endpoint, body) {
        const formData = new URLSearchParams();
        Object.entries(body).forEach(([key, value]) => formData.append(key, value));
        return this.request(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: formData,
        });
    }

    static postMultipart(endpoint, formData, options = {}) {
        return this.request(endpoint, { method: "POST", body: formData, ...options });
    }

    static download(endpoint) {
        return this.request(endpoint, { method: "GET", responseType: "blob", timeoutMs: 60_000 });
    }
}
