import { Suspense, lazy } from "react";
import {
    createBrowserRouter,
    createHashRouter,
    RouterProvider,
} from "react-router";
import { Login } from "./components/Login";
import { RecoveryShell } from "./components/RecoveryShell";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ToastProvider } from "./context/ToastContext";
import { isDesktopShell } from "./platform/desktop";
import { useI18n } from "./i18n/useI18n";

const AuthenticatedWorkspace = lazy(() => import("./app/AuthenticatedWorkspace").then((module) => ({ default: module.AuthenticatedWorkspace })));

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
                <AuthenticatedWorkspace />
            </Suspense>
        </ToastProvider>
    );
}

function AppProviders() {
    return (
        <AuthProvider>
            <AuthenticatedApp />
        </AuthProvider>
    );
}

const createRouter = isDesktopShell() ? createHashRouter : createBrowserRouter;
const applicationRouter = createRouter([
    {
        path: "*",
        element: <AppProviders />,
    },
]);

export default function App() {
    return <RouterProvider router={applicationRouter} />;
}
