import { ApiClient } from "../lib/client";

export const AuthService = {
    _refreshPromise: null,
    _logoutToken: null,

    async login(username, password) {
        // Account transitions supersede every older request/refresh epoch. A
        // late response can no longer remount or overwrite the new identity.
        ApiClient.invalidateSession();
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
            this._logoutToken = null;
            ApiClient.setToken(resData.access_token);
        }
        return resData;
    },

    async register(username, password) {
        ApiClient.invalidateSession();
        const sessionEpoch = ApiClient.getSessionEpoch();
        const resData = await ApiClient.post("/auth/register", { username, password }, {
            suppressGlobalError: true,
            suppressUnauthorizedRefresh: true,
        });
        if (!ApiClient.isSessionEpoch(sessionEpoch)) return null;
        if (resData.access_token) {
            this._logoutToken = null;
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
                    this._logoutToken = null;
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
        const logoutToken = this._logoutToken || ApiClient.getToken();
        this._logoutToken = logoutToken;
        ApiClient.invalidateSession();
        const options = {
            suppressGlobalError: true,
            suppressUnauthorizedRefresh: true,
        };
        if (logoutToken) {
            options.headers = { Authorization: `Bearer ${logoutToken}` };
        }
        await ApiClient.post("/auth/logout", {}, options);
        this._logoutToken = null;
    },

    prepareLogout() {
        if (!this._logoutToken) {
            this._logoutToken = ApiClient.getToken();
        }
        ApiClient.invalidateSession();
    },

    discardLogoutToken() {
        this._logoutToken = null;
        ApiClient.invalidateSession();
    },

    isLoggedIn() {
        return !!ApiClient.getToken();
    }
};
