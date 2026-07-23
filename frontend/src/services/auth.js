import { ApiClient } from "../lib/client";

export const AuthService = {
    async login(username, password) {
        const resData = await ApiClient.postForm("/auth/login", { username, password });
        if (resData.access_token) {
            ApiClient.setToken(resData.access_token);
        }
        return resData;
    },

    async register(username, password) {
        const resData = await ApiClient.post("/auth/register", { username, password });
        if (resData.access_token) {
            ApiClient.setToken(resData.access_token);
        }
        return resData;
    },

    async refresh() {
        ApiClient._suppressUnauthorized = true;
        try {
            const resData = await ApiClient.post("/auth/refresh", {});
            if (resData.access_token) {
                ApiClient.setToken(resData.access_token);
                return resData;
            }
        } catch (error) {
            ApiClient.setToken(null);
            throw error;
        } finally {
            ApiClient._suppressUnauthorized = false;
        }
    },

    async logout() {
        ApiClient._suppressUnauthorized = true;
        try {
            await ApiClient.post("/auth/logout", {});
        } catch {
            // Logout failure is non-critical
        } finally {
            ApiClient._suppressUnauthorized = false;
        }
        ApiClient.setToken(null);
    },

    isLoggedIn() {
        return !!ApiClient.getToken();
    }
};
