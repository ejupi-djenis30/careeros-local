/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
    const [toast, setToast] = useState(null);
    const hideTimeoutRef = useRef(null);

    const showToast = useCallback((message, type = 'danger', action = null, duration = 5000) => {
        setToast({ message, type, action });
        if (hideTimeoutRef.current) {
            clearTimeout(hideTimeoutRef.current);
        }
        hideTimeoutRef.current = setTimeout(() => setToast(null), duration);
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
            const message = event?.detail?.message;
            if (message) {
                showToast(message);
            }
        };

        window.addEventListener('jh_api_error', handleApiError);
        return () => {
            window.removeEventListener('jh_api_error', handleApiError);
            if (hideTimeoutRef.current) {
                clearTimeout(hideTimeoutRef.current);
            }
        };
    }, [showToast]);

    return (
        <ToastContext.Provider value={{ toast, showToast, clearToast }}>
            {children}
            {/* Global Toast Renderer */}
            {toast && (
                <div className="position-fixed bottom-0 end-0 p-3" style={{ zIndex: 1055 }}>
                    <div className={`toast show align-items-center text-bg-${toast.type} border-0`} role="alert">
                        <div className="d-flex">
                            <div className="toast-body">{toast.message}</div>
                            {toast.action && (
                                <button
                                    type="button"
                                    className="btn btn-sm btn-link text-white fw-bold text-decoration-none pe-2 flex-shrink-0"
                                    onClick={() => { toast.action.onAction(); clearToast(); }}
                                >
                                    {toast.action.label}
                                </button>
                            )}
                            <button
                                type="button"
                                className="btn-close btn-close-white me-2 m-auto"
                                onClick={clearToast}
                                aria-label="Close"
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
