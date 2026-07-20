/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useState, useEffect } from 'react';
import { AuthService } from '../services/auth';
import { CAREEROS_UNAUTHORIZED_EVENT } from '../lib/events';
import { useI18n } from '../i18n/useI18n';

const AuthContext = createContext(null);

function requireAccessToken(response, fallbackMessageKey, t) {
    if (response?.access_token) {
        return response;
    }

    const message = response?.detail || response?.error || response?.message;
    if (message) throw new Error(message);
    const error = new Error(t(fallbackMessageKey));
    error.messageKey = fallbackMessageKey;
    throw error;
}

export function AuthProvider({ children }) {
    const { t } = useI18n();
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    const logout = async () => {
        await AuthService.logout();
        setUser(null);
    };

    useEffect(() => {
        const initAuth = async () => {
            try {
                const res = await AuthService.refresh();
                if (res && res.username) {
                    setUser(res.username);
                }
            } catch {
                // No active session
            } finally {
                setLoading(false);
            }
        };

        const handleUnauthorized = () => {
            console.warn("Session expired or unauthorized. Logging out.");
            logout();
        };

        window.addEventListener(CAREEROS_UNAUTHORIZED_EVENT, handleUnauthorized);
        initAuth();

        return () => window.removeEventListener(CAREEROS_UNAUTHORIZED_EVENT, handleUnauthorized);
    }, []);

    const login = async (username, password) => {
        const res = requireAccessToken(
            await AuthService.login(username, password),
            "auth.loginFailed",
            t
        );
        setUser(username);
        return res;
    };

    const register = async (username, password) => {
        const res = requireAccessToken(
            await AuthService.register(username, password),
            "auth.registrationFailed",
            t
        );
        setUser(username);
        return res;
    };

    if (loading) {
        return (
            <div className="min-vh-100 d-flex align-items-center justify-content-center" style={{ background: 'var(--bg-body)' }}>
                <div className="text-center">
                    <div className="spinner-border text-primary mb-3" style={{ width: '3rem', height: '3rem' }} role="status">
                        <span className="visually-hidden">{t("auth.loading")}</span>
                    </div>
                    <p className="text-secondary fw-medium mb-0">{t("auth.loadingSession")}</p>
                </div>
            </div>
        );
    }

    return (
        <AuthContext.Provider value={{ user, login, register, logout, isLoggedIn: !!user }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
}
