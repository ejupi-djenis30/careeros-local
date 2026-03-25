export const API_BASE = import.meta.env.VITE_API_URL || "/api/v1";

export class ApiClient {
    static accessToken = null;
    static _refreshPromise = null;

    static _dispatchApiError(message) {
        window.dispatchEvent(new CustomEvent("jh_api_error", { detail: { message } }));
    }

    static _extractErrorMessage(errorData, fallbackMessage) {
        let errMsg = fallbackMessage;
        if (errorData.detail) {
            if (typeof errorData.detail === 'string') errMsg = errorData.detail;
            else if (Array.isArray(errorData.detail)) errMsg = errorData.detail.map(e => e.msg).join(", ");
            else errMsg = JSON.stringify(errorData.detail);
        } else if (errorData.message) {
            errMsg = errorData.message;
        }
        return errMsg;
    }

    static setToken(token) {
        this.accessToken = token;
    }

    static getToken() {
        return this.accessToken;
    }

    static getHeaders() {
        const token = this.getToken();
        const headers = {
            "Content-Type": "application/json",
        };
        if (token) {
            headers["Authorization"] = `Bearer ${token}`;
        }
        return headers;
    }

    static async _handleUnauthorized(originalUrl, originalConfig) {
        if (!this._refreshPromise) {
            this._refreshPromise = (async () => {
                const refreshRes = await fetch(`${API_BASE}/auth/refresh`, {
                    method: 'POST',
                    credentials: 'include'
                });
                if (!refreshRes.ok) {
                    return null;
                }
                const refreshData = await refreshRes.json();
                if (!refreshData.access_token) {
                    return null;
                }
                this.setToken(refreshData.access_token);
                return refreshData.access_token;
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
            const newHeaders = {
                ...originalConfig.headers,
                "Authorization": `Bearer ${refreshedToken}`
            };
            return await fetch(originalUrl, { ...originalConfig, headers: newHeaders });
        }

        window.dispatchEvent(new Event("jh_unauthorized"));
        return null;
    }

    static async request(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const config = {
            credentials: 'include',
            ...options,
            headers: {
                ...this.getHeaders(),
                ...options.headers,
            },
        };

        let response = await fetch(url, config);

        if (response.status === 401) {
            const retryRes = await this._handleUnauthorized(url, config);
            if (retryRes) response = retryRes;
            else throw new Error("UNAUTHORIZED");
        }

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            const errMsg = this._extractErrorMessage(errorData, "API Request Failed");
            this._dispatchApiError(errMsg);
            throw new Error(errMsg);
        }

        if (response.status === 204) return null;
        return response.json();
    }

    static async get(endpoint) {
        return this.request(endpoint, { method: "GET" });
    }

    static async post(endpoint, body) {
        return this.request(endpoint, {
            method: "POST",
            body: JSON.stringify(body),
        });
    }

    static async postForm(endpoint, body) {
        const formData = new URLSearchParams();
        for (const key in body) {
            formData.append(key, body[key]);
        }
        return this.request(endpoint, {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body: formData,
        });
    }

    static async postMultipart(endpoint, formData) {
        return this.request(endpoint, {
            method: "POST",
            headers: {},
            body: formData,
        });
    }

    static async patch(endpoint, body) {
        return this.request(endpoint, {
            method: "PATCH",
            body: JSON.stringify(body),
        });
    }

    static async delete(endpoint) {
        return this.request(endpoint, { method: "DELETE" });
    }
}
