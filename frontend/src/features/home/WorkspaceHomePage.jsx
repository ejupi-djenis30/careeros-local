import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { useI18n } from "../../i18n/useI18n";
import { CareerService } from "../../services/career";
import { ResumeService } from "../../services/resumes";
import { ApplicationService } from "../../services/applications";
import { SearchService } from "../../services/search";
import { ModelManager } from "../local-model/ModelManager";
import { useLocalModelStatus } from "../local-model/useLocalModelStatus";
import { getStageLabels } from "../applications/applicationModel";
import { DataRecoveryPanel } from "./DataRecoveryPanel";

const loadingSource = () => ({ state: "loading", value: null });
const INITIAL_SOURCES = {
    profile: loadingSource(),
    resumes: loadingSource(),
    applications: loadingSource(),
    searchOverview: loadingSource(),
    searchStatuses: loadingSource(),
};

function settledSource(result, { missingOn404 = false, fallback = null } = {}) {
    if (result.status === "fulfilled") return { state: "ready", value: result.value ?? fallback };
    if (missingOn404 && result.reason?.status === 404) return { state: "missing", value: null };
    return { state: "unavailable", value: fallback };
}

function usableFacts(profile) {
    return (profile?.facts || []).filter(fact => (
        fact?.verification_status === "confirmed" && !fact?.payload?.archived
    ));
}

function statusCopyKey(state) {
    return `home.setup.status.${state}`;
}

function GuidanceChecklist({ milestones, applications, onRetry }) {
    const { t } = useI18n();
    const completed = milestones.filter(item => item.state === "complete").length;
    const allComplete = completed === milestones.length;
    const activeApplications = applications.filter(item => !["accepted", "rejected", "withdrawn", "archived"].includes(item.current_stage));

    if (allComplete) {
        const hasActiveApplications = activeApplications.length > 0;
        return (
            <section className="home-guidance home-guidance--complete" aria-labelledby="home-guidance-title">
                <div className="home-guidance__complete-mark" aria-hidden="true"><i className="bi bi-check-lg" /></div>
                <div>
                    <span className="section-kicker">{t("home.setup.readyKicker")}</span>
                    <h2 id="home-guidance-title">{t("home.setup.readyTitle")}</h2>
                    <p>{hasActiveApplications
                        ? t("home.setup.readyApplications", { count: activeApplications.length })
                        : t("home.setup.readyJobs")}</p>
                </div>
                <Link className="button button--primary" to={hasActiveApplications ? "/applications" : "/jobs"}>
                    {hasActiveApplications ? t("home.setup.reviewApplications") : t("home.setup.reviewJobs")}
                    <i className="bi bi-arrow-right" aria-hidden="true" />
                </Link>
            </section>
        );
    }

    const currentIndex = milestones.findIndex(item => !["complete", "loading"].includes(item.state));
    const progressive = milestones.map((item, index) => ({ ...item, current: index === currentIndex }));

    return (
        <section className="surface-section home-guidance" aria-labelledby="home-guidance-title" aria-busy={milestones.some(item => item.state === "loading") || undefined}>
            <div className="home-guidance__heading">
                <div>
                    <span className="section-kicker">{t("home.setup.kicker")}</span>
                    <h2 id="home-guidance-title">{t("home.setup.title")}</h2>
                    <p>{t("home.setup.copy")}</p>
                </div>
                <span className="home-guidance__verified">{t("home.setup.verified", { count: completed })}</span>
            </div>

            <ol className="home-checklist">
                {progressive.map((item, index) => (
                    <li key={item.key} className={`home-checklist__item is-${item.state} ${item.current ? "is-current" : ""}`}>
                        <span className="home-checklist__marker" aria-hidden="true">
                            {item.state === "complete" && <i className="bi bi-check-lg" />}
                            {item.state === "loading" && <span className="spinner-border spinner-border-sm" />}
                            {item.state === "unavailable" && <i className="bi bi-exclamation-lg" />}
                            {item.state === "unknown" && <i className="bi bi-question-lg" />}
                            {item.state === "pending" && index + 1}
                        </span>
                        <div className="home-checklist__body">
                            <div>
                                <h3>{item.title}</h3>
                                <span className={`home-checklist__status is-${item.state}`}>{t(statusCopyKey(item.state))}</span>
                            </div>
                            <p>{item.copy}</p>
                        </div>
                        {item.to && item.state !== "complete" && (
                            <div className="home-checklist__actions">
                                {item.anchor
                                    ? <a className="button button--secondary button--small" href={item.to}>{item.action}<i className="bi bi-arrow-down" aria-hidden="true" /></a>
                                    : <Link className="button button--secondary button--small" to={item.to}>{item.action}<i className="bi bi-arrow-right" aria-hidden="true" /></Link>}
                                {item.secondaryTo && (
                                    <Link className="home-checklist__secondary" to={item.secondaryTo}>
                                        {item.secondaryAction}
                                    </Link>
                                )}
                            </div>
                        )}
                        {item.state === "unavailable" && (
                            <button type="button" className="button button--secondary button--small" onClick={item.onRetry || onRetry}>
                                {t("home.setup.retry")}<i className="bi bi-arrow-clockwise" aria-hidden="true" />
                            </button>
                        )}
                    </li>
                ))}
            </ol>
        </section>
    );
}

export function WorkspaceHomePage() {
    const { language, t } = useI18n();
    const [sources, setSources] = useState(INITIAL_SOURCES);
    const [refreshRevision, setRefreshRevision] = useState(0);
    const { status: modelStatus, refresh: refreshModel } = useLocalModelStatus({ refreshMs: 30_000 });

    useEffect(() => {
        let active = true;
        const controller = new AbortController();
        const quietOptions = { signal: controller.signal, suppressGlobalError: true };
        Promise.allSettled([
            CareerService.getProfile(quietOptions),
            ResumeService.list(quietOptions),
            ApplicationService.list(quietOptions),
            SearchService.getProfileOverview(quietOptions),
            SearchService.getAllStatuses(controller.signal, { suppressGlobalError: true }),
        ]).then(([profile, resumes, applications, searchOverview, searchStatuses]) => {
            if (!active) return;
            setSources({
                profile: settledSource(profile, { missingOn404: true }),
                resumes: settledSource(resumes, { fallback: [] }),
                applications: settledSource(applications, { fallback: [] }),
                searchOverview: settledSource(searchOverview, {
                    fallback: {
                        items: [],
                        aggregate: { total_profiles: 0, total_successful_runs: 0 },
                    },
                }),
                searchStatuses: settledSource(searchStatuses, { fallback: {} }),
            });
        });
        return () => {
            active = false;
            controller.abort();
        };
    }, [refreshRevision]);

    const retryHomeState = () => {
        setSources(INITIAL_SOURCES);
        setRefreshRevision(value => value + 1);
    };

    const profile = sources.profile.state === "ready" ? sources.profile.value : null;
    const resumes = useMemo(() => sources.resumes.state === "ready" ? sources.resumes.value : [], [sources.resumes]);
    const applications = useMemo(() => sources.applications.state === "ready" ? sources.applications.value : [], [sources.applications]);
    const confirmedFacts = useMemo(() => usableFacts(profile), [profile]);
    const published = useMemo(() => resumes.filter(resume => resume.latest_version).length, [resumes]);
    const activeApplications = useMemo(() => applications.filter(application => !["accepted", "rejected", "withdrawn", "archived"].includes(application.current_stage)), [applications]);
    const recent = useMemo(() => [...applications].sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at)).slice(0, 4), [applications]);
    const stageLabels = getStageLabels(t);
    const locale = language === "it" ? "it-IT" : "en-GB";

    const vaultMilestone = (() => {
        if (sources.profile.state === "loading") return { key: "vault", state: "loading", title: t("home.setup.vaultChecking"), copy: t("home.setup.checkingCopy") };
        if (sources.profile.state === "unavailable") return { key: "vault", state: "unavailable", title: t("home.setup.vaultUnavailable"), copy: t("home.setup.unavailableCopy") };
        if (sources.profile.state === "missing" || confirmedFacts.length === 0) return {
            key: "vault",
            state: "pending",
            title: t("home.setup.vaultPending"),
            copy: t("home.setup.vaultPendingCopy"),
            to: "/profile?start=import",
            action: t("home.setup.vaultImportAction"),
            secondaryTo: "/profile",
            secondaryAction: t("home.setup.vaultManualAction"),
        };
        return { key: "vault", state: "complete", title: t("home.setup.vaultComplete"), copy: t("home.setup.vaultCompleteCopy", { count: confirmedFacts.length }) };
    })();

    const modelMilestone = (() => {
        if (modelStatus.loading) return { key: "model", state: "loading", title: t("home.setup.modelChecking"), copy: t("home.setup.checkingCopy") };
        if (modelStatus.error_code === "local_service_unreachable") return { key: "model", state: "unavailable", title: t("home.setup.modelUnavailable"), copy: t("home.setup.unavailableCopy"), onRetry: refreshModel };
        if (!modelStatus.ready) return { key: "model", state: "pending", title: t("home.setup.modelPending"), copy: t("home.setup.modelPendingCopy"), to: "#home-model-setup", action: t("home.setup.modelAction"), anchor: true };
        return { key: "model", state: "complete", title: t("home.setup.modelComplete"), copy: t("home.setup.modelCompleteCopy", { model: modelStatus.configured_model || t("model.runtime") }) };
    })();

    const searchMilestone = (() => {
        const statusesAvailable = sources.searchStatuses.state === "ready";
        const overviewAvailable = sources.searchOverview.state === "ready";
        if (sources.searchStatuses.state === "loading" || sources.searchOverview.state === "loading") return { key: "search", state: "loading", title: t("home.setup.searchChecking"), copy: t("home.setup.checkingCopy") };
        const aggregate = overviewAvailable ? sources.searchOverview.value?.aggregate : null;
        const completedRuns = Number(aggregate?.total_successful_runs);
        if (Number.isFinite(completedRuns) && completedRuns > 0) {
            const jobsFound = Number(aggregate?.latest_successful_jobs_found);
            const completedAt = Date.parse(aggregate?.latest_successful_completed_at || "");
            const hasDisplayDetails = completedAt > 0 && Number.isFinite(jobsFound);
            return {
                key: "search",
                state: "complete",
                title: t("home.setup.searchComplete"),
                copy: hasDisplayDetails
                    ? t("home.setup.searchCompleteReceiptCopy", {
                        runs: completedRuns,
                        date: new Date(completedAt).toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" }),
                        count: Math.max(0, jobsFound),
                    })
                    : t("home.setup.searchCompleteDurableCopy", { runs: completedRuns }),
            };
        }
        const completedStatuses = statusesAvailable
            ? Object.values(sources.searchStatuses.value || {}).filter(status => status?.state === "done")
            : [];
        if (completedStatuses.length > 0) {
            const latest = [...completedStatuses].sort((left, right) => String(right.finished_at || "").localeCompare(String(left.finished_at || "")))[0];
            return { key: "search", state: "complete", title: t("home.setup.searchComplete"), copy: t("home.setup.searchCompleteCopy", { count: Number(latest.jobs_found || 0) }) };
        }
        if (!statusesAvailable || !overviewAvailable) return { key: "search", state: "unavailable", title: t("home.setup.searchUnavailable"), copy: t("home.setup.unavailableCopy") };
        if (Number(aggregate?.total_profiles || 0) > 0) return { key: "search", state: "unknown", title: t("home.setup.searchUnknown"), copy: t("home.setup.searchUnknownCopy"), to: "/history", action: t("home.setup.searchReview") };
        return { key: "search", state: "pending", title: t("home.setup.searchPending"), copy: t("home.setup.searchPendingCopy"), to: "/new", action: t("home.setup.searchAction") };
    })();

    const applicationMilestone = (() => {
        if (sources.applications.state === "loading") return { key: "application", state: "loading", title: t("home.setup.applicationChecking"), copy: t("home.setup.checkingCopy") };
        if (sources.applications.state === "unavailable") return { key: "application", state: "unavailable", title: t("home.setup.applicationUnavailable"), copy: t("home.setup.unavailableCopy") };
        if (applications.length === 0) return { key: "application", state: "pending", title: t("home.setup.applicationPending"), copy: t("home.setup.applicationPendingCopy"), to: "/applications", action: t("home.setup.applicationAction") };
        return { key: "application", state: "complete", title: t("home.setup.applicationComplete"), copy: t("home.setup.applicationCompleteCopy", { count: applications.length }) };
    })();

    const milestones = [vaultMilestone, modelMilestone, searchMilestone, applicationMilestone];
    const profileUnavailable = ["loading", "unavailable"].includes(sources.profile.state);
    const vaultReady = vaultMilestone.state === "complete";

    return (
        <div className="home-grid">
            <section className="home-hero">
                <div>
                    <span className="section-kicker">
                        {profile ? t("home.profileRevision", { revision: profile.revision }) : sources.profile.state === "missing" ? t("home.startHere") : t("page.home.eyebrow")}
                    </span>
                    <h2>{profile ? t("home.welcome", { name: profile.display_name }) : sources.profile.state === "missing" ? t("home.buildMemory") : t("page.home.title")}</h2>
                    <p>{profile?.headline || (profileUnavailable ? t("home.dataChecking") : t("home.fallbackSummary"))}</p>
                </div>
                <div className="home-hero__actions">
                    {vaultReady && <Link className="button button--primary" to="/coach">{t("home.talkCoach")}</Link>}
                    {profile && <Link className={`button ${vaultReady ? "button--secondary" : "button--primary"}`} to="/profile">{vaultReady ? t("home.updateProfile") : t("home.setup.vaultAction")}</Link>}
                    {sources.profile.state === "missing" && <Link className="button button--primary" to="/profile">{t("home.createVault")}</Link>}
                    {sources.profile.state === "unavailable" && <button type="button" className="button button--secondary" onClick={retryHomeState}>{t("home.setup.retry")}</button>}
                </div>
                <div className="home-hero__orb" aria-hidden="true"><span>C</span></div>
            </section>

            <GuidanceChecklist milestones={milestones} applications={applications} onRetry={retryHomeState} />

            <section className="metric-grid" aria-label={t("home.summary")}>
                <Link to="/profile" className="metric-card"><i className="bi bi-database-check" /><span>{t("home.vaultFacts")}</span><strong>{sources.profile.state === "ready" ? (profile?.facts || []).length : "—"}</strong><small>{t("home.goals")}: {sources.profile.state === "ready" ? profile?.goals?.length || 0 : "—"}</small></Link>
                <Link to="/resumes" className="metric-card"><i className="bi bi-file-earmark-check" /><span>{t("home.publishedResumes")}</span><strong>{sources.resumes.state === "ready" ? published : "—"}</strong><small>{t("home.drafts")}: {sources.resumes.state === "ready" ? resumes.length : "—"}</small></Link>
                <Link to="/applications" className="metric-card"><i className="bi bi-send-check" /><span>{t("home.activeApplications")}</span><strong>{sources.applications.state === "ready" ? activeApplications.length : "—"}</strong><small>{sources.applications.state === "ready" ? applications.length : "—"} {t("home.total")}</small></Link>
                <Link to="/jobs" className="metric-card metric-card--action"><i className="bi bi-radar" /><span>{t("home.opportunityEngine")}</span><strong>{t("home.open")}</strong><small>{t("home.localSearch")}</small></Link>
            </section>

            <section className="surface-section home-activity">
                <div className="section-heading"><div><span className="section-kicker">{t("home.pipeline")}</span><h2>{t("home.recentActivity")}</h2></div><Link to="/applications">{t("home.viewAll")}</Link></div>
                {sources.applications.state === "unavailable"
                    ? <div className="home-source-unavailable" role="status"><p>{t("home.activityUnavailable")}</p><button type="button" className="button button--secondary button--small" onClick={retryHomeState}>{t("home.setup.retry")}</button></div>
                    : recent.length
                        ? <div className="recent-list">{recent.map(application => <Link key={application.id} to="/applications"><span className={`stage-dot stage-dot--${application.current_stage}`} /><div><strong>{application.title}</strong><small>{application.company}</small></div><span>{stageLabels[application.current_stage]}</span></Link>)}</div>
                        : <div className="empty-inline"><p>{sources.applications.state === "loading" ? t("home.activityChecking") : t("home.noApplications")}</p></div>}
            </section>

            <section id="home-model-setup" className="surface-section home-runtime">
                <div className="section-heading"><div><span className="section-kicker">{t("home.runtime")}</span><h2>{t("home.onDeviceModel")}</h2></div></div>
                <ModelManager status={modelStatus} onRefresh={refreshModel} />
                <div className="local-architecture"><span>Career Vault</span><i className="bi bi-arrow-right" /><span>{t("home.chosenContext")}</span><i className="bi bi-arrow-right" /><span>{t("home.localLlama")}</span></div>
                <p>{t("home.modelDisclosure")}</p>
            </section>
            <DataRecoveryPanel hasProfile={Boolean(profile)} onErased={retryHomeState} />
        </div>
    );
}
