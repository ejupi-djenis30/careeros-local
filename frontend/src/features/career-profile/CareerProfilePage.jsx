import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../../lib/client";
import { CareerService } from "../../services/career";
import { ResumeService } from "../../services/resumes";
import { useAuth } from "../../context/AuthContext";
import { useToast } from "../../context/ToastContext";
import { useI18n } from "../../i18n/useI18n";
import { FactsEditor } from "./FactsEditor";
import { GoalsEditor } from "./GoalsEditor";
import { IdentityEditor } from "./IdentityEditor";
import { PreferencesEditor } from "./PreferencesEditor";
import { SourceImporter } from "./SourceImporter";
import { emptyProfile, profileCompleteness, profileDraftToWrite, profileResponseToDraft } from "./profileModel";

export function CareerProfilePage() {
    const { user } = useAuth();
    const { showToast } = useToast();
    const { t } = useI18n();
    const [profile, setProfile] = useState(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [dirty, setDirty] = useState(false);
    const [error, setError] = useState("");
    const [conflict, setConflict] = useState(false);
    const [jobSources, setJobSources] = useState([]);
    const [resumeVersions, setResumeVersions] = useState([]);
    const profileRequestRef = useRef({ controller: null, id: 0 });
    const sectionLabels = {
        identity: t("profile.section.identity"),
        experience: t("profile.section.experience"),
        skills: t("profile.section.skills"),
        education: t("profile.section.education"),
        achievements: t("profile.section.achievements"),
        projects: t("profile.section.projects"),
        credentials_activities: t("profile.section.credentials"),
        preferences: t("profile.section.preferences"),
        goals: t("profile.section.goals"),
    };
    const issueLabels = {
        overlapping_primary_employment: t("profile.issue.overlap"),
        future_historical_date: t("profile.issue.future"),
        possible_duplicate_fact: t("profile.issue.duplicate"),
        missing_evidence: t("profile.issue.evidence"),
    };

    const requestProfile = useCallback(() => {
        const requestId = profileRequestRef.current.id + 1;
        profileRequestRef.current.controller?.abort();
        const controller = new AbortController();
        profileRequestRef.current = { controller, id: requestId };
        const requestOptions = { signal: controller.signal, suppressGlobalError: true };
        const sourceRequest = Promise.resolve()
            .then(() => CareerService.getJobSources(requestOptions))
            .catch(() => []);
        const versionRequest = Promise.resolve()
            .then(() => ResumeService.listVersions(requestOptions))
            .catch(() => []);
        const profileRequest = Promise.resolve()
            .then(() => CareerService.getProfile(requestOptions))
            .then((response) => ({ profile: profileResponseToDraft(response) }))
            .catch((loadError) => {
                if (loadError instanceof ApiError && loadError.status === 404) {
                    return { profile: emptyProfile(user) };
                }
                return { error: loadError };
            });

        return Promise.all([profileRequest, sourceRequest, versionRequest])
            .then(([profileResult, nextJobSources, nextResumeVersions]) => {
                if (controller.signal.aborted || profileRequestRef.current.id !== requestId) return;
                if (profileResult.error) {
                    setError(profileResult.error.message);
                } else {
                    setProfile(profileResult.profile);
                    setError("");
                    setConflict(false);
                    setDirty(false);
                }
                setJobSources(nextJobSources);
                setResumeVersions(nextResumeVersions);
                setLoading(false);
                profileRequestRef.current.controller = null;
            });
    }, [user]);

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        setConflict(false);
        return requestProfile();
    }, [requestProfile]);

    useEffect(() => {
        void requestProfile();
        return () => {
            profileRequestRef.current.id += 1;
            profileRequestRef.current.controller?.abort();
            profileRequestRef.current.controller = null;
        };
    }, [requestProfile]);
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
            showToast(t("profile.importReady", { count: additions.length }), "success");
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
            showToast(t("profile.savedToast"), "success");
        } catch (saveError) {
            if (saveError instanceof ApiError && saveError.status === 409) setConflict(true);
            setError(saveError.message);
        } finally {
            setSaving(false);
        }
    };

    if (loading) return <div className="page-loader" role="status"><span className="spinner-border" /><span>{t("profile.loading")}</span></div>;
    if (!profile) return <div className="state-panel state-panel--danger"><h2>{t("profile.unavailable")}</h2><p>{error}</p><button className="button button--secondary" onClick={load}>{t("profile.retry")}</button></div>;

    return (
        <form className="profile-workspace" onSubmit={save}>
            <aside className="profile-rail">
                <div className="profile-score">
                    <span>{t("profile.completeness")}</span><strong>{completeness}%</strong>
                    <div className="profile-score__track"><span style={{ width: `${completeness}%` }} /></div>
                    <p>{t("profile.completenessCopy")}</p>
                    {!dirty && profile.analysis?.missing_sections?.length > 0 && <div className="profile-gaps"><strong>{t("profile.toComplete")}</strong><ul>{profile.analysis.missing_sections.map((section) => <li key={section}>{sectionLabels[section] || section}</li>)}</ul></div>}
                </div>
                {!dirty && profile.analysis?.issues?.length > 0 && <section className="profile-issues" aria-labelledby="profile-issues-title"><strong id="profile-issues-title">{t("profile.recommendedChecks")}</strong><ul>{profile.analysis.issues.slice(0, 5).map((issue, index) => <li key={`${issue.code}-${index}`}>{issueLabels[issue.code] || issue.message}</li>)}</ul></section>}
                <div className="privacy-note"><i className="bi bi-device-ssd" /><div><strong>{t("profile.localVault")}</strong><span>{t("profile.localVaultCopy")}</span></div></div>
                <dl className="revision-meta"><div><dt>{t("profile.revision")}</dt><dd>{profile.expected_revision}</dd></div><div><dt>{t("profile.facts")}</dt><dd>{profile.facts.length}</dd></div><div><dt>{t("profile.goals")}</dt><dd>{profile.goals.length}</dd></div></dl>
            </aside>

            <div className="profile-editor">
                {error && <div className={`inline-alert ${conflict ? "inline-alert--warning" : "inline-alert--danger"}`} role="alert"><div><strong>{conflict ? t("profile.otherSession") : t("profile.saveFailed")}</strong><span>{error}</span></div>{conflict && <button type="button" className="button button--secondary" onClick={load}>{t("profile.reload")}</button>}</div>}
                <IdentityEditor profile={profile} onChange={update} />
                <GoalsEditor goals={profile.goals} facts={profile.facts} resumeVersions={resumeVersions} onChange={(goals) => update({ ...profile, goals })} />
                <PreferencesEditor preferences={profile.preferences} jobSources={jobSources} onChange={(preferences) => update({ ...profile, preferences })} />
                <FactsEditor key={`facts-${profile.expected_revision}`} facts={profile.facts} analysis={profile.analysis} onChange={(facts) => update({ ...profile, facts })} />
                <SourceImporter onAcceptCandidates={acceptSourceCandidates} />
            </div>

            <div className="save-dock" aria-live="polite">
                <div><span className={`save-dock__dot ${dirty ? "is-dirty" : ""}`} /><span>{dirty ? t("profile.unsaved") : t("profile.saved")}</span></div>
                <button type="submit" className="button button--primary" disabled={saving || !dirty || !profile.display_name.trim()}>{saving ? t("profile.saving") : t("profile.save")}</button>
            </div>
        </form>
    );
}
