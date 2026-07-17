import React, { Suspense, lazy } from "react";
import { BrowserRouter, HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { WorkspaceShell } from "./app/WorkspaceShell";
import { Login } from "./components/Login";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { SearchProvider } from "./context/SearchContext";
import { ToastProvider } from "./context/ToastContext";
import { isDesktopShell } from "./platform/desktop";

const ApplicationsPage = lazy(() => import("./features/applications/ApplicationsPage").then((module) => ({ default: module.ApplicationsPage })));
const CareerProfilePage = lazy(() => import("./features/career-profile/CareerProfilePage").then((module) => ({ default: module.CareerProfilePage })));
const WorkspaceHomePage = lazy(() => import("./features/home/WorkspaceHomePage").then((module) => ({ default: module.WorkspaceHomePage })));
const CareerCoachPage = lazy(() => import("./features/local-coach/CareerCoachPage").then((module) => ({ default: module.CareerCoachPage })));
const ResumeStudioPage = lazy(() => import("./features/resume-studio/ResumeStudioPage").then((module) => ({ default: module.ResumeStudioPage })));
const HistoryPage = lazy(() => import("./pages/HistoryPage").then((module) => ({ default: module.HistoryPage })));
const JobsPage = lazy(() => import("./pages/JobsPage").then((module) => ({ default: module.JobsPage })));
const NewSearchPage = lazy(() => import("./pages/NewSearchPage").then((module) => ({ default: module.NewSearchPage })));
const ProgressPage = lazy(() => import("./pages/ProgressPage").then((module) => ({ default: module.ProgressPage })));
const SchedulesPage = lazy(() => import("./pages/SchedulesPage").then((module) => ({ default: module.SchedulesPage })));

class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { error: null };
    }

    static getDerivedStateFromError(error) {
        return { error };
    }

    componentDidCatch(error, info) {
        console.error("Unhandled UI error", error, info.componentStack);
    }

    render() {
        if (this.state.error) {
            return (
                <div className="state-panel state-panel--danger" role="alert">
                    <i className="bi bi-exclamation-triangle" aria-hidden="true" />
                    <h2>Questa vista si è interrotta</h2>
                    <p>I dati locali non sono stati modificati. Ricarica l’interfaccia per riprovare.</p>
                    <button type="button" className="button button--primary" onClick={() => window.location.reload()}>Ricarica applicazione</button>
                </div>
            );
        }
        return this.props.children;
    }
}
function AuthenticatedApp() {
    const { isLoggedIn } = useAuth();
    if (!isLoggedIn) return <Login />;

    return (
        <WorkspaceShell>
            <ErrorBoundary>
                <Suspense fallback={<div className="state-panel" role="status">Caricamento vista locale…</div>}>
                    <Routes>
                        <Route path="/" element={<WorkspaceHomePage />} />
                        <Route path="/profile" element={<CareerProfilePage />} />
                        <Route path="/resumes" element={<ResumeStudioPage />} />
                        <Route path="/applications" element={<ApplicationsPage />} />
                        <Route path="/coach" element={<CareerCoachPage />} />
                        <Route path="/jobs" element={<JobsPage />} />
                        <Route path="/search" element={<NewSearchPage />} />
                        <Route path="/new" element={<Navigate to="/search" replace />} />
                        <Route path="/schedules" element={<SchedulesPage />} />
                        <Route path="/history" element={<HistoryPage />} />
                        <Route path="/progress" element={<ProgressPage />} />
                        <Route path="*" element={<Navigate to="/" replace />} />
                    </Routes>
                </Suspense>
            </ErrorBoundary>
        </WorkspaceShell>
    );
}

export default function App() {
    const Router = isDesktopShell() ? HashRouter : BrowserRouter;
    return (
        <Router>
            <AuthProvider>
                <SearchProvider>
                    <ToastProvider>
                        <AuthenticatedApp />
                    </ToastProvider>
                </SearchProvider>
            </AuthProvider>
        </Router>
    );
}
