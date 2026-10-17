import { Suspense, lazy } from "react";
import { Login } from "./components/Login";
import { RecoveryShell } from "./components/RecoveryShell";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ToastProvider } from "./context/ToastContext";
import { useI18n } from "./i18n/useI18n";

const AuthenticatedRouter = lazy(() => import("./app/AuthenticatedRouter").then((module) => ({ default: module.AuthenticatedRouter })));

export function AuthenticatedApp() {
    const { isLoggedIn, maintenanceSession } = useAuth();
    const { t } = useI18n();
    if (maintenanceSession) return <RecoveryShell />;
    if (!isLoggedIn) return <Login />;

    return (
        <ToastProvider>
            <Suspense fallback={(
                <div className="session-loader" role="status">
                    <span className="spinner-border" aria-hidden="true" />
                    <span>{t("shell.loading")}</span>
                </div>
            )}>
                <AuthenticatedRouter />
            </Suspense>
        </ToastProvider>
    );
}

export default function App() {
    return (
        <AuthProvider>
            <AuthenticatedApp />
        </AuthProvider>
    );
}
