/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useState, useEffect } from 'react';
import { AuthService } from '../services/auth';

const AuthContext = createContext(null);

function requireAccessToken(response, fallbackMessage) {
    if (response?.access_token) {
        return response;
    }

    const message = response?.detail || response?.error || response?.message || fallbackMessage;
    throw new Error(message);
}

export function AuthProvider({ children }) {
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

        window.addEventListener("jh_unauthorized", handleUnauthorized);
        initAuth();

        return () => window.removeEventListener("jh_unauthorized", handleUnauthorized);
    }, []);

    const login = async (username, password) => {
        const res = requireAccessToken(
            await AuthService.login(username, password),
            'Login failed. Please try again.'
        );
        setUser(username);
        return res;
    };

    const register = async (username, password) => {
        const res = requireAccessToken(
            await AuthService.register(username, password),
            'Registration failed. Please try again.'
        );
        setUser(username);
        return res;
    };

    if (loading) {
        return (
            <div className="min-vh-100 d-flex align-items-center justify-content-center" style={{ background: 'var(--bg-body)' }}>
                <div className="text-center">
                    <div className="spinner-border text-primary mb-3" style={{ width: '3rem', height: '3rem' }} role="status">
                        <span className="visually-hidden">Loading...</span>
                    </div>
                    <p className="text-secondary fw-medium mb-0">Loading session...</p>
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
