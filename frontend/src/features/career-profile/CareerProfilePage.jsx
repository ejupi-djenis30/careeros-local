import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "../../lib/client";
import { CareerService } from "../../services/career";
import { ResumeService } from "../../services/resumes";
import { useAuth } from "../../context/AuthContext";
import { useToast } from "../../context/ToastContext";
import { FactsEditor } from "./FactsEditor";
import { GoalsEditor } from "./GoalsEditor";
import { IdentityEditor } from "./IdentityEditor";
import { PreferencesEditor } from "./PreferencesEditor";
import { SourceImporter } from "./SourceImporter";
import { emptyProfile, profileCompleteness, profileDraftToWrite, profileResponseToDraft } from "./profileModel";

const SECTION_LABELS = {
    identity: "Identità",
    experience: "Esperienze",
    skills: "Competenze",
    education: "Formazione",
    achievements: "Risultati",
    projects: "Progetti",
    credentials_activities: "Credenziali e attività",
    preferences: "Preferenze",
    goals: "Obiettivi",
};

const ISSUE_LABELS = {
    overlapping_primary_employment: "Due esperienze principali hanno date sovrapposte.",
    future_historical_date: "Un evento storico ha una data futura.",
    possible_duplicate_fact: "Alcuni fatti potrebbero essere duplicati.",
    missing_evidence: "Una bozza non ha ancora un’evidenza.",
};

export function CareerProfilePage() {
    const { user } = useAuth();
    const { showToast } = useToast();
    const [profile, setProfile] = useState(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [dirty, setDirty] = useState(false);
    const [error, setError] = useState("");
    const [conflict, setConflict] = useState(false);
    const [jobSources, setJobSources] = useState([]);
    const [resumeVersions, setResumeVersions] = useState([]);

    const load = useCallback(async () => {
        setLoading(true);
        setError("");
        setConflict(false);
        const sourceRequest = CareerService.getJobSources({ suppressGlobalError: true })
            .catch(() => []);
        const versionRequest = ResumeService.listVersions().catch(() => []);
        try {
            const response = await CareerService.getProfile({ suppressGlobalError: true });
            setProfile(profileResponseToDraft(response));
            setDirty(false);
        } catch (loadError) {
            if (loadError instanceof ApiError && loadError.status === 404) {
                setProfile(emptyProfile(user));
                setDirty(false);
            } else {
                setError(loadError.message);
            }
        } finally {
            setJobSources(await sourceRequest);
            setResumeVersions(await versionRequest);
            setLoading(false);
        }
    }, [user]);

    useEffect(() => { load(); }, [load]);
    useEffect(() => {
        const guard = (event) => { if (dirty) event.preventDefault(); };
        window.addEventListener("beforeunload", guard);
        return () => window.removeEventListener("beforeunload", guard);
    }, [dirty]);

    const completeness = useMemo(() => {
        if (!profile) return 0;
        if (!dirty && profile.analysis) return profile.analysis.completeness_score;
        return profileCompleteness(profile);
    }, [dirty, profile]);
    const update = (next) => { setProfile(next); setDirty(true); setConflict(false); };

    const acceptSourceCandidates = (document, candidates) => {
        const existing = new Set(profile.facts.map((fact) => (
            `${fact.source_document_id || ""}|${fact.source_locator || ""}|${fact.fact_type}`
        )));
        const additions = candidates.filter((candidate) => {
            const key = `${document.id}|${candidate.source_locator}|${candidate.fact_type}`;
            if (existing.has(key)) return false;
            existing.add(key);
            return true;
        }).map((candidate, index) => ({
            clientKey: crypto.randomUUID(),
            fact_type: candidate.fact_type,
            position: profile.facts.length + index,
            payload: structuredClone(candidate.payload),
            source_document_id: document.id,
            source_locator: candidate.source_locator,
            confidence: candidate.confidence,
            verification_status: "imported",
        }));
        if (additions.length > 0) {
            update({ ...profile, facts: [...profile.facts, ...additions] });
            showToast(`${additions.length} fatti importati pronti per la revisione.`, "success");
        }
        return additions.length;
    };

    const save = async (event) => {
        event.preventDefault();
        setSaving(true);
        setError("");
        setConflict(false);
        try {
            const response = await CareerService.saveProfile(profileDraftToWrite(profile));
            setProfile(profileResponseToDraft(response));
            setDirty(false);
            window.dispatchEvent(new Event("careeros:profile-updated"));
            showToast("Career Vault salvato sul dispositivo.", "success");
        } catch (saveError) {
            if (saveError instanceof ApiError && saveError.status === 409) setConflict(true);
            setError(saveError.message);
        } finally {
            setSaving(false);
        }
    };

    if (loading) return <div className="page-loader" role="status"><span className="spinner-border" /><span>Carico il Career Vault…</span></div>;
    if (!profile) return <div className="state-panel state-panel--danger"><h2>Profilo non disponibile</h2><p>{error}</p><button className="button button--secondary" onClick={load}>Riprova</button></div>;

    return (
        <form className="profile-workspace" onSubmit={save}>
            <aside className="profile-rail">
                <div className="profile-score">
                    <span>Completezza</span><strong>{completeness}%</strong>
                    <div className="profile-score__track"><span style={{ width: `${completeness}%` }} /></div>
                    <p>Più fatti confermati significano CV e suggerimenti più precisi.</p>
                    {!dirty && profile.analysis?.missing_sections?.length > 0 && <div className="profile-gaps"><strong>Da completare</strong><ul>{profile.analysis.missing_sections.map((section) => <li key={section}>{SECTION_LABELS[section] || section}</li>)}</ul></div>}
                </div>
                {!dirty && profile.analysis?.issues?.length > 0 && <section className="profile-issues" aria-labelledby="profile-issues-title"><strong id="profile-issues-title">Controlli consigliati</strong><ul>{profile.analysis.issues.slice(0, 5).map((issue, index) => <li key={`${issue.code}-${index}`}>{ISSUE_LABELS[issue.code] || issue.message}</li>)}</ul></section>}
                <div className="privacy-note"><i className="bi bi-device-ssd" /><div><strong>Vault locale</strong><span>SQLite + file system. Nessun dato inviato a servizi AI remoti.</span></div></div>
                <dl className="revision-meta"><div><dt>Revisione</dt><dd>{profile.expected_revision}</dd></div><div><dt>Fatti</dt><dd>{profile.facts.length}</dd></div><div><dt>Obiettivi</dt><dd>{profile.goals.length}</dd></div></dl>
            </aside>

            <div className="profile-editor">
                {error && <div className={`inline-alert ${conflict ? "inline-alert--warning" : "inline-alert--danger"}`} role="alert"><div><strong>{conflict ? "Il profilo è cambiato in un’altra sessione." : "Salvataggio non riuscito"}</strong><span>{error}</span></div>{conflict && <button type="button" className="button button--secondary" onClick={load}>Ricarica versione corrente</button>}</div>}
                <IdentityEditor profile={profile} onChange={update} />
                <GoalsEditor goals={profile.goals} facts={profile.facts} resumeVersions={resumeVersions} onChange={(goals) => update({ ...profile, goals })} />
                <PreferencesEditor preferences={profile.preferences} jobSources={jobSources} onChange={(preferences) => update({ ...profile, preferences })} />
                <FactsEditor key={`facts-${profile.expected_revision}`} facts={profile.facts} analysis={profile.analysis} onChange={(facts) => update({ ...profile, facts })} />
                <SourceImporter onAcceptCandidates={acceptSourceCandidates} />
            </div>

            <div className="save-dock" aria-live="polite">
                <div><span className={`save-dock__dot ${dirty ? "is-dirty" : ""}`} /><span>{dirty ? "Modifiche non salvate" : "Tutto salvato localmente"}</span></div>
                <button type="submit" className="button button--primary" disabled={saving || !dirty || !profile.display_name.trim()}>{saving ? "Salvataggio…" : "Salva Career Vault"}</button>
            </div>
        </form>
    );
}
