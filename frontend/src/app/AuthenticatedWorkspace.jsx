import React, { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router";
import { SearchProvider } from "../context/SearchContext";
import { useI18n } from "../i18n/useI18n";
import { RequiredLocalAnalysis } from "../features/local-model/RequiredLocalAnalysis";
import { WorkspaceShell } from "./WorkspaceShell";
import "../bootstrap-icons-subset.css";
import "../index.css";
import "../career-os.css";
import "./workspace-bootstrap.css";

const ApplicationsPage = lazy(() => import("../features/applications/ApplicationsPage").then((module) => ({ default: module.ApplicationsPage })));
const AgentAccessPage = lazy(() => import("../features/agent-access/AgentAccessPage").then((module) => ({ default: module.AgentAccessPage })));
const CareerProfilePage = lazy(() => import("../features/career-profile/CareerProfilePage").then((module) => ({ default: module.CareerProfilePage })));
const WorkspaceHomePage = lazy(() => import("../features/home/WorkspaceHomePage").then((module) => ({ default: module.WorkspaceHomePage })));
const CareerCoachPage = lazy(() => import("../features/local-coach/CareerCoachPage").then((module) => ({ default: module.CareerCoachPage })));
const ResumeStudioPage = lazy(() => import("../features/resume-studio/ResumeStudioPage").then((module) => ({ default: module.ResumeStudioPage })));
const HistoryPage = lazy(() => import("../pages/HistoryPage").then((module) => ({ default: module.HistoryPage })));
const JobsPage = lazy(() => import("../pages/JobsPage").then((module) => ({ default: module.JobsPage })));
const NewSearchPage = lazy(() => import("../pages/NewSearchPage").then((module) => ({ default: module.NewSearchPage })));
const ProgressPage = lazy(() => import("../pages/ProgressPage").then((module) => ({ default: module.ProgressPage })));
const SchedulesPage = lazy(() => import("../pages/SchedulesPage").then((module) => ({ default: module.SchedulesPage })));

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
                    <h2>{this.props.title}</h2>
                    <p>{this.props.description}</p>
                    <button type="button" className="button button--primary" onClick={() => window.location.reload()}>{this.props.reloadLabel}</button>
                </div>
            );
        }
        return this.props.children;
    }
}

export function AuthenticatedWorkspace() {
    const { t } = useI18n();

    return (
        <SearchProvider>
            <WorkspaceShell>
                <ErrorBoundary title={t("shell.errorTitle")} description={t("shell.errorCopy")} reloadLabel={t("shell.reload")}>
                    <Suspense fallback={<div className="state-panel" role="status">{t("shell.loading")}</div>}>
                        <Routes>
                            <Route path="/" element={<WorkspaceHomePage />} />
                            <Route path="/profile" element={<CareerProfilePage />} />
                            <Route path="/resumes" element={<ResumeStudioPage />} />
                            <Route path="/applications" element={<ApplicationsPage />} />
                            <Route path="/agent-access" element={<AgentAccessPage />} />
                            <Route path="/coach" element={<RequiredLocalAnalysis><CareerCoachPage /></RequiredLocalAnalysis>} />
                            <Route path="/jobs" element={<JobsPage />} />
                            <Route path="/search" element={<RequiredLocalAnalysis><NewSearchPage /></RequiredLocalAnalysis>} />
                            <Route path="/new" element={<Navigate to="/search" replace />} />
                            <Route path="/schedules" element={<SchedulesPage />} />
                            <Route path="/history" element={<RequiredLocalAnalysis><HistoryPage /></RequiredLocalAnalysis>} />
                            <Route path="/progress" element={<ProgressPage />} />
                            <Route path="*" element={<Navigate to="/" replace />} />
                        </Routes>
                    </Suspense>
                </ErrorBoundary>
            </WorkspaceShell>
        </SearchProvider>
    );
}
