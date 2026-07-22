import { useState } from "react";
import { safeExternalUrl } from "../../lib/safeUrl";
import { ApplicationService } from "../../services/applications";
import { TRANSITIONS, getStageLabels } from "./applicationModel";
import { useI18n } from "../../i18n/useI18n";
import { ApplicationReadiness } from "./ApplicationReadiness";
import { ApplicationPreparationForm } from "./ApplicationPreparationForm";

export function ApplicationDetail({ application, resumeVersions = [], onChanged, onClose, dialogRef }) {
    const { language, t } = useI18n();
    const locale = language === "it" ? "it-IT" : "en-GB";
    const stageLabels = getStageLabels(t);
    const eventLabels = Object.fromEntries(["stage", "note", "task", "contact", "interview", "preparation"].map((type) => [type, t(`applicationEvent.${type}`)]));
    const [eventType, setEventType] = useState(TRANSITIONS[application.current_stage].length ? "stage" : "note");
    const [stage, setStage] = useState(TRANSITIONS[application.current_stage][0] || "");
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [editingPreparation, setEditingPreparation] = useState(false);
    const snapshot = application.job_snapshot || {};
    const url = safeExternalUrl(snapshot.application_url) || safeExternalUrl(snapshot.external_url);
    const availableTransitions = TRANSITIONS[application.current_stage];
    const activeEventType = eventType === "stage" && availableTransitions.length === 0 ? "note" : eventType;
    const activeStage = availableTransitions.includes(stage) ? stage : availableTransitions[0] || "";

    const submit = async (event) => {
        event.preventDefault();
        setBusy(true);
        setError("");
        try {
            const payload = {
                expected_revision: application.revision,
                event_type: activeEventType,
                payload: {},
                note: note.trim() || null,
            };
            if (activeEventType === "stage") payload.stage = activeStage;
            const updated = await ApplicationService.addEvent(application.id, payload);
            setNote("");
            onChanged(updated);
        } catch (submitError) {
            setError(submitError.status === 409 ? t("applicationDetail.conflict") : submitError.message);
        } finally {
            setBusy(false);
        }
    };

    return (
        <div ref={dialogRef} className="application-detail" role="dialog" aria-modal="true" aria-labelledby="application-detail-title" aria-describedby="application-detail-summary" tabIndex="-1">
            <header><div><span className={`stage-badge stage-badge--${application.current_stage}`}>{stageLabels[application.current_stage]}</span><h2 id="application-detail-title">{snapshot.title || t("applicationDetail.fallbackTitle")}</h2><p id="application-detail-summary">{snapshot.company}{snapshot.location ? ` · ${snapshot.location}` : ""}</p></div><button type="button" className="icon-button" data-dialog-initial-focus onClick={onClose} aria-label={t("applicationDetail.close")}><i className="bi bi-x-lg" /></button></header>
            <div className="application-snapshot"><div><i className="bi bi-camera" /><span><strong>{t("applicationDetail.snapshot")}</strong><small>{t("applicationDetail.snapshotCopy")}</small></span></div>{url && <a className="button button--secondary" href={url} target="_blank" rel="noopener noreferrer">{t("applicationDetail.openSource")} <i className="bi bi-box-arrow-up-right" /></a>}</div>
            {editingPreparation && <ApplicationPreparationForm key={application.revision} application={application} resumeVersions={resumeVersions} onUpdated={onChanged} onClose={() => setEditingPreparation(false)} />}
            <ApplicationReadiness applicationId={application.id} applicationRevision={application.revision} onEditPreparation={() => setEditingPreparation(true)} />
            {error && <div className="inline-alert inline-alert--danger" role="alert">{error}</div>}
            <form className="application-event-form" onSubmit={submit}>
                <h3>{t("applicationDetail.addEvent")}</h3>
                <div className="form-grid form-grid--2">
                    <label className="field-stack"><span>{t("applicationDetail.eventType")}</span><select className="form-select" value={activeEventType} onChange={(e) => { setEventType(e.target.value); if (e.target.value === "stage") setStage(availableTransitions[0] || ""); }}>{Object.entries(eventLabels).filter(([value]) => value !== "preparation" && (value !== "stage" || availableTransitions.length)).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                    {activeEventType === "stage" && <label className="field-stack"><span>{t("applicationDetail.newStage")}</span><select className="form-select" value={activeStage} onChange={(e) => setStage(e.target.value)}>{availableTransitions.map((value) => <option key={value} value={value}>{stageLabels[value]}</option>)}</select></label>}
                </div>
                <label className="field-stack"><span>{activeEventType === "task" ? t("applicationDetail.activity") : t("applicationDetail.note")}</span><textarea className="form-control" rows="3" value={note} onChange={(e) => setNote(e.target.value)} required={["note", "contact", "interview"].includes(activeEventType)} placeholder={t("applicationDetail.placeholder")} /></label>
                <button className="button button--primary" disabled={busy || (activeEventType === "stage" && !activeStage)}>{busy ? t("applicationDetail.recording") : t("applicationDetail.record")}</button>
            </form>
            <section className="application-timeline" aria-labelledby="timeline-title"><h3 id="timeline-title">{t("applicationDetail.timeline")}</h3>{[...application.events].reverse().map((entry) => <article key={entry.id}><span className="timeline-dot" /><div><header><strong>{entry.event_type === "stage" ? stageLabels[entry.stage] : eventLabels[entry.event_type]}</strong><time dateTime={entry.occurred_at}>{new Date(entry.occurred_at).toLocaleString(locale)}</time></header>{entry.note && <p>{entry.note}</p>}</div></article>)}</section>
        </div>
    );
}
