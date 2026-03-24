export const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

export class ApiClient {
    static accessToken = null;
    static _suppressUnauthorized = false;

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
        if (this._suppressUnauthorized) return null;
        this._suppressUnauthorized = true;
        try {
            const refreshRes = await fetch(`${API_BASE}/auth/refresh`, {
                method: 'POST',
                credentials: 'include'
            });
            if (refreshRes.ok) {
                const refreshData = await refreshRes.json();
                if (refreshData.access_token) {
                    this.setToken(refreshData.access_token);
                    this._suppressUnauthorized = false;
                    
                    // Retry original request
                    const newHeaders = {
                        ...originalConfig.headers,
                        "Authorization": `Bearer ${refreshData.access_token}`
                    };
                    return await fetch(originalUrl, { ...originalConfig, headers: newHeaders });
                }
            }
        } catch (e) {
            // fall through
        } finally {
            this._suppressUnauthorized = false;
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
            let errMsg = "API Request Failed";
            if (errorData.detail) {
                if (typeof errorData.detail === 'string') errMsg = errorData.detail;
                else if (Array.isArray(errorData.detail)) errMsg = errorData.detail.map(e => e.msg).join(", ");
                else errMsg = JSON.stringify(errorData.detail);
            } else if (errorData.message) {
                errMsg = errorData.message;
            }
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
        const url = `${API_BASE}${endpoint}`;
        const config = {
            method: "POST",
            credentials: 'include',
            headers: {
                // Manual token for multipart since we don't want JSON Content-Type
                "Authorization": this.getToken() ? `Bearer ${this.getToken()}` : undefined
            },
            body: formData,
        };

        let response = await fetch(url, config);

        if (response.status === 401) {
            const retryRes = await this._handleUnauthorized(url, config);
            if (retryRes) response = retryRes;
            else throw new Error("UNAUTHORIZED");
        }

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            let errMsg = "Upload Failed";
            if (errorData.detail) errMsg = typeof errorData.detail === 'string' ? errorData.detail : JSON.stringify(errorData.detail);
            throw new Error(errMsg);
        }

        if (response.status === 204) return null;
        return response.json();
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
