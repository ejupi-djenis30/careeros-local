/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useState, useEffect } from 'react';
import { AuthService } from '../services/auth';

const AuthContext = createContext(null);

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
            } catch (err) {
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
        const res = await AuthService.login(username, password);
        if (res.access_token) {
            setUser(username);
        }
        return res;
    };

    const register = async (username, password) => {
        const res = await AuthService.register(username, password);
        if (res.access_token) {
            setUser(username);
        }
        return res;
    };

    if (loading) {
        return <div className="flex h-screen items-center justify-center font-medium text-zinc-500 dark:bg-zinc-950 dark:text-zinc-400">Loading session...</div>;
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
