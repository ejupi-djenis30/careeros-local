import { CAREEROS_API_ERROR_EVENT, CAREEROS_UNAUTHORIZED_EVENT } from "./events";

const DEFAULT_API_BASE = "/api/v1";
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);
const SESSION_INVALIDATED_REASON = "session-invalidated";
const CALLER_ABORTED_REASON = "caller-aborted";
const REQUEST_TIMEOUT_REASON = "request-timeout";

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
    ApiClient.invalidateSession();
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
    static _refreshController = null;
    static _sessionEpoch = 0;
    static _activeControllers = new Set();

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
        if (!token) {
            this.invalidateSession();
            return;
        }
        this.accessToken = token;
    }

    static invalidateSession() {
        this._sessionEpoch += 1;
        this.accessToken = null;
        this._refreshController?.abort(SESSION_INVALIDATED_REASON);
        this._refreshController = null;
        this._refreshPromise = null;
        for (const controller of this._activeControllers) {
            controller.abort(SESSION_INVALIDATED_REASON);
        }
    }

    static getSessionEpoch() {
        return this._sessionEpoch;
    }

    static isSessionEpoch(epoch) {
        return epoch === this._sessionEpoch;
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

    static async _handleUnauthorized(originalUrl, originalConfig, requestEpoch) {
        if (!this.isSessionEpoch(requestEpoch) || originalConfig.signal?.aborted) {
            return null;
        }
        if (!this._refreshPromise) {
            const refreshEpoch = this._sessionEpoch;
            const refreshController = new AbortController();
            this._refreshController = refreshController;
            this._refreshPromise = (async () => {
                const response = await fetch(`${getApiBase()}/auth/refresh`, {
                    method: "POST",
                    credentials: "include",
                    headers: this.getHeaders({ json: false }),
                    signal: refreshController.signal,
                });
                if (!response.ok) return null;
                const data = await response.json();
                if (!data.access_token) return null;
                if (!this.isSessionEpoch(refreshEpoch) || refreshController.signal.aborted) {
                    return null;
                }
                this.accessToken = data.access_token;
                return data.access_token;
            })();
        }

        const refreshPromise = this._refreshPromise;
        let refreshedToken = null;
        try {
            refreshedToken = await refreshPromise;
        } catch {
            refreshedToken = null;
        } finally {
            if (this._refreshPromise === refreshPromise) {
                this._refreshPromise = null;
                this._refreshController = null;
            }
        }

        if (
            refreshedToken &&
            this.isSessionEpoch(requestEpoch) &&
            !originalConfig.signal?.aborted
        ) {
            return fetch(originalUrl, {
                ...originalConfig,
                headers: { ...originalConfig.headers, Authorization: `Bearer ${refreshedToken}` },
            });
        }

        if (
            this.isSessionEpoch(requestEpoch)
            && !originalConfig.signal?.aborted
        ) {
            window.dispatchEvent(new Event(CAREEROS_UNAUTHORIZED_EVENT));
        }
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
        const requestEpoch = this._sessionEpoch;
        this._activeControllers.add(controller);
        const timeoutMs = options.timeoutMs ?? 30_000;
        const timeoutId = setTimeout(
            () => controller.abort(REQUEST_TIMEOUT_REASON),
            timeoutMs,
        );
        const callerSignal = options.signal;
        const abortFromCaller = () => controller.abort(CALLER_ABORTED_REASON);
        callerSignal?.addEventListener("abort", abortFromCaller, { once: true });
        if (callerSignal?.aborted) controller.abort(CALLER_ABORTED_REASON);

        const {
            signal: _ignoredSignal,
            timeoutMs: _ignoredTimeout,
            suppressGlobalError = false,
            suppressUnauthorizedRefresh = false,
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
            if (response.status === 401 && !suppressUnauthorizedRefresh) {
                response = await this._handleUnauthorized(url, config, requestEpoch);
                if (!response) throw new ApiError("UNAUTHORIZED", { status: 401 });
            }

            if (!response.ok) {
                const details = await this._parseError(response);
                if (!this.isSessionEpoch(requestEpoch)) {
                    throw new ApiError("SESSION_CHANGED", { status: 0 });
                }
                const message = this._extractErrorMessage(details, `Request failed (${response.status})`);
                if (!suppressGlobalError) this._dispatchApiError(message);
                throw new ApiError(message, { status: response.status, details });
            }

            if (response.status === 204) {
                if (!this.isSessionEpoch(requestEpoch)) {
                    throw new ApiError("SESSION_CHANGED", { status: 0 });
                }
                return null;
            }
            if (responseType === "blob") {
                const result = {
                    blob: await response.blob(),
                    filename: this._filenameFromResponse(response),
                    sha256: response.headers.get("X-Content-SHA256"),
                };
                if (!this.isSessionEpoch(requestEpoch)) {
                    throw new ApiError("SESSION_CHANGED", { status: 0 });
                }
                return result;
            }
            const result = await response.json();
            if (!this.isSessionEpoch(requestEpoch)) {
                throw new ApiError("SESSION_CHANGED", { status: 0 });
            }
            return result;
        } catch (error) {
            if (controller.signal.aborted) {
                if (controller.signal.reason === SESSION_INVALIDATED_REASON) {
                    throw new ApiError("SESSION_CHANGED", { status: 0 });
                }
                if (controller.signal.reason === CALLER_ABORTED_REASON) {
                    throw new DOMException("The request was cancelled", "AbortError");
                }
                throw new ApiError("The local service did not respond in time", { status: 0 });
            }
            if (error?.name === "AbortError") {
                throw new ApiError("The local service did not respond in time", { status: 0 });
            }
            throw error;
        } finally {
            clearTimeout(timeoutId);
            callerSignal?.removeEventListener("abort", abortFromCaller);
            this._activeControllers.delete(controller);
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

    static postForm(endpoint, body, options = {}) {
        const formData = new URLSearchParams();
        Object.entries(body).forEach(([key, value]) => formData.append(key, value));
        return this.request(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: formData,
            ...options,
        });
    }

    static postMultipart(endpoint, formData, options = {}) {
        return this.request(endpoint, { method: "POST", body: formData, ...options });
    }

    static download(endpoint) {
        return this.request(endpoint, { method: "GET", responseType: "blob", timeoutMs: 60_000 });
    }
}
