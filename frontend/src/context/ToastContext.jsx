/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { CAREEROS_API_ERROR_EVENT } from '../lib/events';
import { useI18n } from '../i18n/useI18n';
import { translateMessage } from '../i18n/runtime';

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
    const { t } = useI18n();
    const [toast, setToast] = useState(null);
    const hideTimeoutRef = useRef(null);

    const showToast = useCallback((message, type = 'danger', action = null, duration = 5000) => {
        setToast({ message, type, action });
        if (hideTimeoutRef.current) {
            clearTimeout(hideTimeoutRef.current);
        }
        hideTimeoutRef.current = setTimeout(() => {
            hideTimeoutRef.current = null;
            setToast(null);
        }, duration);
    }, []);

    const clearToast = useCallback(() => {
        if (hideTimeoutRef.current) {
            clearTimeout(hideTimeoutRef.current);
            hideTimeoutRef.current = null;
        }
        setToast(null);
    }, []);

    useEffect(() => {
        const handleApiError = (event) => {
            const detail = event?.detail;
            if (detail?.messageKey || detail?.message) {
                showToast({
                    messageKey: detail.messageKey,
                    variables: detail.variables,
                    message: detail.message,
                });
            }
        };

        window.addEventListener(CAREEROS_API_ERROR_EVENT, handleApiError);
        return () => window.removeEventListener(CAREEROS_API_ERROR_EVENT, handleApiError);
    }, [showToast]);

    useEffect(() => () => {
        if (hideTimeoutRef.current) {
            clearTimeout(hideTimeoutRef.current);
        }
    }, []);

    return (
        <ToastContext.Provider value={{ toast, showToast, clearToast }}>
            {children}
            {/* Global Toast Renderer */}
            {toast && (
                <div className="position-fixed bottom-0 end-0 p-3" style={{ zIndex: 1055 }}>
                    <div className={`toast show align-items-center text-bg-${toast.type} border-0`} role="alert">
                        <div className="d-flex">
                            <div className="toast-body">{translateMessage(toast.message, t)}</div>
                            {toast.action && (
                                <button
                                    type="button"
                                    className="btn btn-sm btn-link text-white fw-bold text-decoration-none pe-2 flex-shrink-0"
                                    onClick={() => { toast.action.onAction(); clearToast(); }}
                                >
                                    {translateMessage(
                                        toast.action.labelKey
                                            ? { messageKey: toast.action.labelKey, variables: toast.action.variables }
                                            : toast.action.label,
                                        t,
                                    )}
                                </button>
                            )}
                            <button
                                type="button"
                                className="btn-close btn-close-white me-2 m-auto"
                                onClick={clearToast}
                                aria-label={t("common.close")}
                            ></button>
                        </div>
                    </div>
                </div>
            )}
        </ToastContext.Provider>
    );
}

export function useToast() {
    const context = useContext(ToastContext);
    if (!context) {
        throw new Error('useToast must be used within a ToastProvider');
    }
    return context;
}
