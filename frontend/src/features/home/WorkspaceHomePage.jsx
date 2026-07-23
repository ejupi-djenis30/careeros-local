import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useI18n } from "../../i18n/useI18n";
import { CareerService } from "../../services/career";
import { ResumeService } from "../../services/resumes";
import { ApplicationService } from "../../services/applications";
import { ModelManager } from "../local-model/ModelManager";
import { getStageLabels } from "../applications/applicationModel";
import { DataRecoveryPanel } from "./DataRecoveryPanel";

const EMPTY = { profile: null, resumes: [], applications: [] };

export function WorkspaceHomePage() {
    const { t } = useI18n();
    const [data, setData] = useState(EMPTY);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let active = true;
        Promise.allSettled([
            CareerService.getSummary({ suppressGlobalError: true }),
            ResumeService.list(),
            ApplicationService.list(),
        ]).then(([profile, resumes, applications]) => {
            if (!active) return;
            setData({
                profile: profile.status === "fulfilled" ? profile.value : null,
                resumes: resumes.status === "fulfilled" ? resumes.value : [],
                applications: applications.status === "fulfilled" ? applications.value : [],
            });
            setLoading(false);
        });
        return () => { active = false; };
    }, []);

    const published = useMemo(() => data.resumes.filter((resume) => resume.latest_version).length, [data.resumes]);
    const activeApplications = useMemo(() => data.applications.filter((application) => !["accepted", "rejected", "withdrawn", "archived"].includes(application.current_stage)), [data.applications]);
    const recent = [...data.applications].sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at)).slice(0, 4);
    const stageLabels = getStageLabels(t);

    return (
        <div className="home-grid">
            <section className="home-hero">
                <div><span className="section-kicker">{data.profile ? t("home.profileRevision", { revision: data.profile.revision }) : t("home.startHere")}</span><h2>{data.profile ? t("home.welcome", { name: data.profile.display_name }) : t("home.buildMemory")}</h2><p>{data.profile?.headline || t("home.fallbackSummary")}</p></div>
                <div className="home-hero__actions">{data.profile ? <><Link className="button button--primary" to="/coach">{t("home.talkCoach")}</Link><Link className="button button--secondary" to="/profile">{t("home.updateProfile")}</Link></> : <Link className="button button--primary" to="/profile">{t("home.createVault")}</Link>}</div>
                <div className="home-hero__orb" aria-hidden="true"><span>C</span></div>
            </section>

            <section className="metric-grid" aria-label={t("home.summary")}>
                <Link to="/profile" className="metric-card"><i className="bi bi-database-check" /><span>{t("home.vaultFacts")}</span><strong>{loading ? "—" : Object.values(data.profile?.fact_counts || {}).reduce((sum, value) => sum + value, 0)}</strong><small>{data.profile?.goal_count || 0} {t("home.goals")}</small></Link>
                <Link to="/resumes" className="metric-card"><i className="bi bi-file-earmark-check" /><span>{t("home.publishedResumes")}</span><strong>{loading ? "—" : published}</strong><small>{data.resumes.length} {t("home.drafts")}</small></Link>
                <Link to="/applications" className="metric-card"><i className="bi bi-send-check" /><span>{t("home.activeApplications")}</span><strong>{loading ? "—" : activeApplications.length}</strong><small>{data.applications.length} {t("home.total")}</small></Link>
                <Link to="/jobs" className="metric-card metric-card--action"><i className="bi bi-radar" /><span>{t("home.opportunityEngine")}</span><strong>{t("home.open")}</strong><small>{t("home.localSearch")}</small></Link>
            </section>

            <section className="surface-section home-next"><div className="section-heading"><div><span className="section-kicker">{t("home.focus")}</span><h2>{t("home.nextMove")}</h2></div></div><div className="next-actions">{!data.profile && <Link to="/profile"><span>1</span><div><strong>{t("home.completeVault")}</strong><p>{t("home.completeVaultCopy")}</p></div><i className="bi bi-arrow-right" /></Link>}{data.profile && published === 0 && <Link to="/resumes"><span>1</span><div><strong>{t("home.publishAts")}</strong><p>{t("home.publishAtsCopy")}</p></div><i className="bi bi-arrow-right" /></Link>}{data.profile && published > 0 && activeApplications.length === 0 && <Link to="/jobs"><span>1</span><div><strong>{t("home.selectOpportunity")}</strong><p>{t("home.selectOpportunityCopy")}</p></div><i className="bi bi-arrow-right" /></Link>}{activeApplications.length > 0 && <Link to="/applications"><span>1</span><div><strong>{t("home.updatePipeline")}</strong><p>{t("home.applicationsNeedStep", { count: activeApplications.length })}</p></div><i className="bi bi-arrow-right" /></Link>}<Link to="/coach"><span>2</span><div><strong>{t("home.prepareDecision")}</strong><p>{t("home.prepareDecisionCopy")}</p></div><i className="bi bi-arrow-right" /></Link></div></section>

            <section className="surface-section home-activity"><div className="section-heading"><div><span className="section-kicker">{t("home.pipeline")}</span><h2>{t("home.recentActivity")}</h2></div><Link to="/applications">{t("home.viewAll")}</Link></div>{recent.length ? <div className="recent-list">{recent.map((application) => <Link key={application.id} to="/applications"><span className={`stage-dot stage-dot--${application.current_stage}`} /><div><strong>{application.title}</strong><small>{application.company}</small></div><span>{stageLabels[application.current_stage]}</span></Link>)}</div> : <div className="empty-inline"><p>{t("home.noApplications")}</p></div>}</section>

            <section className="surface-section home-runtime"><div className="section-heading"><div><span className="section-kicker">{t("home.runtime")}</span><h2>{t("home.onDeviceModel")}</h2></div></div><ModelManager /><div className="local-architecture"><span>Career Vault</span><i className="bi bi-arrow-right" /><span>{t("home.chosenContext")}</span><i className="bi bi-arrow-right" /><span>{t("home.localLlama")}</span></div><p>{t("home.modelDisclosure")}</p></section>
            <DataRecoveryPanel hasProfile={Boolean(data.profile)} onErased={() => setData(EMPTY)} />
        </div>
    );
}
