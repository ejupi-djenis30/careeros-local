/* eslint-disable react-refresh/only-export-components */
import React, {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useRef,
    useState,
} from 'react';
import { flushSync } from 'react-dom';
import { AuthService } from '../services/auth';
import {
    CAREEROS_BEFORE_LOGOUT_EVENT,
    CAREEROS_MAINTENANCE_COMPLETE_EVENT,
    CAREEROS_MAINTENANCE_PENDING_EVENT,
    CAREEROS_UNAUTHORIZED_EVENT,
} from '../lib/events';
import { useI18n } from '../i18n/useI18n';

const AuthContext = createContext(null);
const MAINTENANCE_SESSION_STATES = new Set([
    "reset_pending",
    "restore_pending",
    "erasure_pending",
]);

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

function maintenanceState(response, invalidMessage = "Unsupported recovery state") {
    const state = response?.session_state;
    if (state == null) return null;
    if (MAINTENANCE_SESSION_STATES.has(state)) return state;
    const error = new Error(invalidMessage);
    error.messageKey = "auth.sessionStateInvalid";
    throw error;
}

export function AuthProvider({ children }) {
    const { t } = useI18n();
    const [user, setUser] = useState(null);
    const [maintenanceSession, setMaintenanceSession] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loggingOut, setLoggingOut] = useState(false);
    const [logoutFailed, setLogoutFailed] = useState(false);
    const [sessionNotice, setSessionNotice] = useState(null);
    const logoutPromiseRef = useRef(null);
    const logoutRetryRef = useRef(null);
    const logoutForcedRef = useRef(false);
    const transitionGenerationRef = useRef(0);

    const logout = useCallback(function performLogout(options = {}) {
        const force = options?.force === true;
        if (logoutPromiseRef.current) {
            if (!force || logoutForcedRef.current) return logoutPromiseRef.current;
            return logoutPromiseRef.current.then((completed) => (
                completed ? true : performLogout({ force: true })
            ));
        }
        logoutForcedRef.current = force;
        const operation = (async () => {
            const waiters = [];
            const event = new CustomEvent(CAREEROS_BEFORE_LOGOUT_EVENT, {
                cancelable: true,
                detail: {
                    force,
                    waitUntil(waiter) {
                        waiters.push(Promise.resolve(waiter));
                    },
                },
            });
            const allowed = window.dispatchEvent(event);
            if (!allowed && !force) return false;

            transitionGenerationRef.current += 1;
            setLogoutFailed(false);
            setLoggingOut(true);
            setUser(null);
            setMaintenanceSession(null);
            if (!force) setSessionNotice(null);
            try {
                await Promise.allSettled(waiters);
                await AuthService.logout();
                return true;
            } catch {
                if (force) AuthService.discardLogoutToken();
                else setLogoutFailed(true);
                return force;
            } finally {
                setLoggingOut(false);
            }
        })();
        const trackedOperation = operation.finally(() => {
            if (logoutPromiseRef.current === trackedOperation) {
                logoutPromiseRef.current = null;
                logoutForcedRef.current = false;
            }
        });
        logoutPromiseRef.current = trackedOperation;
        return trackedOperation;
    }, []);

    useEffect(() => {
        let active = true;
        const initializationGeneration = transitionGenerationRef.current;
        const initAuth = async () => {
            try {
                const res = await AuthService.refresh();
                if (
                    active
                    && transitionGenerationRef.current === initializationGeneration
                    && res
                ) {
                    let state;
                    try {
                        state = maintenanceState(res);
                    } catch (error) {
                        AuthService.prepareLogout();
                        void AuthService.logout().catch(() => {});
                        throw error;
                    }
                    setMaintenanceSession(state ? {
                        sessionState: state,
                        reauthRequired: false,
                    } : null);
                    setUser(state ? null : res.username || null);
                }
            } catch {
                if (
                    active
                    && transitionGenerationRef.current === initializationGeneration
                ) {
                    setUser(null);
                    setMaintenanceSession(null);
                }
            } finally {
                if (active) setLoading(false);
            }
        };

        const handleUnauthorized = (event) => {
            const messageKey = event?.detail?.messageKey;
            transitionGenerationRef.current += 1;
            flushSync(() => {
                setUser(null);
                setMaintenanceSession(null);
                setSessionNotice(typeof messageKey === "string" ? messageKey : null);
            });
            if (!messageKey) console.warn("Session expired or unauthorized. Logging out.");
            logout({ force: true });
        };

        const handleMaintenancePending = (event) => {
            const sessionState = event?.detail?.sessionState;
            if (!MAINTENANCE_SESSION_STATES.has(sessionState)) return;
            transitionGenerationRef.current += 1;
            flushSync(() => {
                setUser(null);
                setMaintenanceSession({
                    sessionState,
                    reauthRequired: event?.detail?.reauthRequired === true,
                });
                setSessionNotice(null);
                setLoading(false);
            });
        };

        const handleMaintenanceComplete = (event) => {
            const messageKey = event?.detail?.messageKey;
            transitionGenerationRef.current += 1;
            flushSync(() => {
                setUser(null);
                setMaintenanceSession(null);
                setSessionNotice(
                    typeof messageKey === "string"
                        ? messageKey
                        : "auth.maintenanceCompleteSignIn",
                );
                setLoading(false);
            });
            logout({ force: true });
        };

        window.addEventListener(CAREEROS_UNAUTHORIZED_EVENT, handleUnauthorized);
        window.addEventListener(CAREEROS_MAINTENANCE_PENDING_EVENT, handleMaintenancePending);
        window.addEventListener(CAREEROS_MAINTENANCE_COMPLETE_EVENT, handleMaintenanceComplete);
        initAuth();

        return () => {
            active = false;
            window.removeEventListener(CAREEROS_UNAUTHORIZED_EVENT, handleUnauthorized);
            window.removeEventListener(CAREEROS_MAINTENANCE_PENDING_EVENT, handleMaintenancePending);
            window.removeEventListener(CAREEROS_MAINTENANCE_COMPLETE_EVENT, handleMaintenanceComplete);
        };
    }, [logout]);

    useEffect(() => {
        if (!logoutFailed) return undefined;
        const frame = window.requestAnimationFrame(() => {
            logoutRetryRef.current?.focus({ preventScroll: true });
        });
        return () => window.cancelAnimationFrame(frame);
    }, [logoutFailed]);

    const login = async (username, password) => {
        const generation = transitionGenerationRef.current + 1;
        transitionGenerationRef.current = generation;
        const response = await AuthService.login(username, password);
        if (transitionGenerationRef.current !== generation) return null;
        const res = requireAccessToken(
            response,
            "auth.loginFailed",
            t
        );
        let state;
        try {
            state = maintenanceState(res, t("auth.sessionStateInvalid"));
        } catch (error) {
            AuthService.prepareLogout();
            void AuthService.logout().catch(() => {});
            throw error;
        }
        setSessionNotice(null);
        setMaintenanceSession(state ? {
            sessionState: state,
            reauthRequired: false,
        } : null);
        setUser(state ? null : username);
        return res;
    };

    const register = async (username, password) => {
        const generation = transitionGenerationRef.current + 1;
        transitionGenerationRef.current = generation;
        const response = await AuthService.register(username, password);
        if (transitionGenerationRef.current !== generation) return null;
        const res = requireAccessToken(
            response,
            "auth.registrationFailed",
            t
        );
        let state;
        try {
            state = maintenanceState(res, t("auth.sessionStateInvalid"));
        } catch (error) {
            AuthService.prepareLogout();
            void AuthService.logout().catch(() => {});
            throw error;
        }
        setSessionNotice(null);
        setMaintenanceSession(state ? {
            sessionState: state,
            reauthRequired: false,
        } : null);
        setUser(state ? null : username);
        return res;
    };

    if (loading || loggingOut) {
        return (
            <div className="session-loader" role="status">
                <span className="spinner-border" aria-hidden="true" />
                <p>{t("auth.loadingSession")}</p>
            </div>
        );
    }

    if (logoutFailed) {
        return (
            <div className="localization-boot localization-boot--error" role="alert">
                <strong>{t("auth.logoutFailedTitle")}</strong>
                <p>{t("auth.logoutFailedCopy")}</p>
                <button
                    ref={logoutRetryRef}
                    type="button"
                    className="button button--primary"
                    onClick={() => { void logout(); }}
                >
                    {t("auth.retryLogout")}
                </button>
            </div>
        );
    }

    return (
        <AuthContext.Provider value={{
            user,
            login,
            register,
            logout,
            isLoggedIn: !!user,
            maintenanceSession,
            sessionNotice,
        }}>
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
