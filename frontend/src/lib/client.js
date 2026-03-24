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

        const response = await fetch(url, config);

        if (response.status === 401) {
            if (!this._suppressUnauthorized) {
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
                            
                            // Retry the original request
                            const newHeaders = {
                                ...config.headers,
                                "Authorization": `Bearer ${refreshData.access_token}`
                            };
                            const retryRes = await fetch(url, { ...config, headers: newHeaders });
                            if (!retryRes.ok) throw new Error("Retry failed");
                            return retryRes.json();
                        }
                    }
                } catch (e) {
                    // fall through
                } finally {
                    this._suppressUnauthorized = false;
                }
                window.dispatchEvent(new Event("jh_unauthorized"));
            }
            throw new Error("UNAUTHORIZED");
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
        const token = this.getToken();
        const headers = {};
        if (token) {
            headers["Authorization"] = `Bearer ${token}`;
        }
        // NOTE: We do NOT set Content-Type for multipart/form-data, 
        // the browser needs to set the boundary.

        const url = `${API_BASE}${endpoint}`;
        const config = {
            method: "POST",
            credentials: 'include',
            headers,
            body: formData,
        };

        const response = await fetch(url, config);

        if (response.status === 401) {
            if (!this._suppressUnauthorized) {
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
                                ...config.headers,
                                "Authorization": `Bearer ${refreshData.access_token}`
                            };
                            const retryRes = await fetch(url, { ...config, headers: newHeaders });
                            if (!retryRes.ok) throw new Error("Retry failed");
                            return retryRes.json();
                        }
                    }
                } catch (e) {
                    // fall through
                } finally {
                    this._suppressUnauthorized = false;
                }
                window.dispatchEvent(new Event("jh_unauthorized"));
            }
            throw new Error("UNAUTHORIZED");
        }

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            let errMsg = "Upload Failed";
            if (errorData.detail) errMsg = typeof errorData.detail === 'string' ? errorData.detail : JSON.stringify(errorData.detail);
            throw new Error(errMsg);
        }

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
