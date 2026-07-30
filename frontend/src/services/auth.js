import { ApiClient } from "../lib/client";

export const AuthService = {
    _refreshPromise: null,

    async login(username, password) {
        const sessionEpoch = ApiClient.getSessionEpoch();
        const resData = await ApiClient.postForm(
            "/auth/login",
            { username, password },
            {
                suppressGlobalError: true,
                suppressUnauthorizedRefresh: true,
            },
        );
        if (!ApiClient.isSessionEpoch(sessionEpoch)) return null;
        if (resData.access_token) {
            ApiClient.setToken(resData.access_token);
        }
        return resData;
    },

    async register(username, password) {
        const sessionEpoch = ApiClient.getSessionEpoch();
        const resData = await ApiClient.post("/auth/register", { username, password }, {
            suppressGlobalError: true,
            suppressUnauthorizedRefresh: true,
        });
        if (!ApiClient.isSessionEpoch(sessionEpoch)) return null;
        if (resData.access_token) {
            ApiClient.setToken(resData.access_token);
        }
        return resData;
    },

    async refresh() {
        if (this._refreshPromise) return this._refreshPromise;
        const sessionEpoch = ApiClient.getSessionEpoch();
        const operation = (async () => {
            try {
                const resData = await ApiClient.post("/auth/refresh", {}, {
                    suppressGlobalError: true,
                    suppressUnauthorizedRefresh: true,
                });
                if (resData.access_token && ApiClient.isSessionEpoch(sessionEpoch)) {
                    ApiClient.setToken(resData.access_token);
                    return resData;
                }
                return null;
            } catch (error) {
                if (ApiClient.isSessionEpoch(sessionEpoch)) {
                    ApiClient.invalidateSession();
                }
                throw error;
            }
        })();
        this._refreshPromise = operation;
        try {
            return await operation;
        } finally {
            if (this._refreshPromise === operation) {
                this._refreshPromise = null;
            }
        }
    },

    async logout() {
        ApiClient.invalidateSession();
        try {
            await ApiClient.post("/auth/logout", {}, {
                suppressGlobalError: true,
                suppressUnauthorizedRefresh: true,
            });
        } catch {
            // Logout failure is non-critical
        }
    },

    isLoggedIn() {
        return !!ApiClient.getToken();
    }
};
