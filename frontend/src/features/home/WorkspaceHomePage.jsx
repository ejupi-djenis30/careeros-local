import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CareerService } from "../../services/career";
import { ResumeService } from "../../services/resumes";
import { ApplicationService } from "../../services/applications";
import { ModelManager } from "../local-model/ModelManager";
import { STAGE_LABELS } from "../applications/applicationModel";
import { DataRecoveryPanel } from "./DataRecoveryPanel";

const EMPTY = { profile: null, resumes: [], applications: [] };

export function WorkspaceHomePage() {
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

    return (
        <div className="home-grid">
            <section className="home-hero">
                <div><span className="section-kicker">{data.profile ? `Profilo r${data.profile.revision}` : "Inizia da qui"}</span><h2>{data.profile ? `Bentornato, ${data.profile.display_name}` : "Costruisci la tua memoria professionale"}</h2><p>{data.profile?.headline || "Un’unica fonte locale per CV, opportunità, candidature e coaching."}</p></div>
                <div className="home-hero__actions">{data.profile ? <><Link className="button button--primary" to="/coach">Parla con il coach</Link><Link className="button button--secondary" to="/profile">Aggiorna profilo</Link></> : <Link className="button button--primary" to="/profile">Crea Career Vault</Link>}</div>
                <div className="home-hero__orb" aria-hidden="true"><span>C</span></div>
            </section>

            <section className="metric-grid" aria-label="Riepilogo workspace">
                <Link to="/profile" className="metric-card"><i className="bi bi-database-check" /><span>Fatti nel Vault</span><strong>{loading ? "—" : Object.values(data.profile?.fact_counts || {}).reduce((sum, value) => sum + value, 0)}</strong><small>{data.profile?.goal_count || 0} obiettivi</small></Link>
                <Link to="/resumes" className="metric-card"><i className="bi bi-file-earmark-check" /><span>CV pubblicati</span><strong>{loading ? "—" : published}</strong><small>{data.resumes.length} bozze</small></Link>
                <Link to="/applications" className="metric-card"><i className="bi bi-send-check" /><span>Candidature attive</span><strong>{loading ? "—" : activeApplications.length}</strong><small>{data.applications.length} totali</small></Link>
                <Link to="/jobs" className="metric-card metric-card--action"><i className="bi bi-radar" /><span>Opportunity engine</span><strong>Apri</strong><small>Ricerca e matching locale</small></Link>
            </section>

            <section className="surface-section home-next"><div className="section-heading"><div><span className="section-kicker">Focus</span><h2>La prossima mossa utile</h2></div></div><div className="next-actions">{!data.profile && <Link to="/profile"><span>1</span><div><strong>Completa il Career Vault</strong><p>Raccogli fatti, risultati e obiettivi verificabili.</p></div><i className="bi bi-arrow-right" /></Link>}{data.profile && published === 0 && <Link to="/resumes"><span>1</span><div><strong>Pubblica un CV ATS</strong><p>Crea una baseline leggibile dai sistemi di selezione.</p></div><i className="bi bi-arrow-right" /></Link>}{data.profile && published > 0 && activeApplications.length === 0 && <Link to="/jobs"><span>1</span><div><strong>Seleziona un’opportunità</strong><p>Trasforma un annuncio in una candidatura tracciabile.</p></div><i className="bi bi-arrow-right" /></Link>}{activeApplications.length > 0 && <Link to="/applications"><span>1</span><div><strong>Aggiorna la pipeline</strong><p>{activeApplications.length} candidature richiedono un prossimo passo.</p></div><i className="bi bi-arrow-right" /></Link>}<Link to="/coach"><span>2</span><div><strong>Prepara una decisione</strong><p>Condividi solo i fatti rilevanti con il modello locale.</p></div><i className="bi bi-arrow-right" /></Link></div></section>

            <section className="surface-section home-activity"><div className="section-heading"><div><span className="section-kicker">Pipeline</span><h2>Attività recente</h2></div><Link to="/applications">Vedi tutto</Link></div>{recent.length ? <div className="recent-list">{recent.map((application) => <Link key={application.id} to="/applications"><span className={`stage-dot stage-dot--${application.current_stage}`} /><div><strong>{application.title}</strong><small>{application.company}</small></div><span>{STAGE_LABELS[application.current_stage]}</span></Link>)}</div> : <div className="empty-inline"><p>Nessuna candidatura registrata.</p></div>}</section>

            <section className="surface-section home-runtime"><div className="section-heading"><div><span className="section-kicker">Runtime</span><h2>Modello sul dispositivo</h2></div></div><ModelManager /><div className="local-architecture"><span>Career Vault</span><i className="bi bi-arrow-right" /><span>Contesto scelto</span><i className="bi bi-arrow-right" /><span>llama.cpp locale</span></div><p>Il modello non riceve automaticamente l’intero profilo: ogni conversazione dichiara i fatti e gli annunci autorizzati.</p></section>
            <DataRecoveryPanel hasProfile={Boolean(data.profile)} onErased={() => setData(EMPTY)} />
        </div>
    );
}
