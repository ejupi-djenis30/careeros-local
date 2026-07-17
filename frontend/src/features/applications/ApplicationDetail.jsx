import { useState } from "react";
import { safeExternalUrl } from "../../lib/safeUrl";
import { ApplicationService } from "../../services/applications";
import { STAGE_LABELS, TRANSITIONS } from "./applicationModel";

const EVENT_LABELS = { stage: "Cambio fase", note: "Nota", task: "Attività", contact: "Contatto", interview: "Colloquio" };

export function ApplicationDetail({ application, onChanged, onClose }) {
    const [eventType, setEventType] = useState(TRANSITIONS[application.current_stage].length ? "stage" : "note");
    const [stage, setStage] = useState(TRANSITIONS[application.current_stage][0] || "");
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const snapshot = application.job_snapshot || {};
    const url = safeExternalUrl(snapshot.application_url) || safeExternalUrl(snapshot.external_url);

    const submit = async (event) => {
        event.preventDefault();
        setBusy(true);
        setError("");
        try {
            const payload = {
                expected_revision: application.revision,
                event_type: eventType,
                payload: {},
                note: note.trim() || null,
            };
            if (eventType === "stage") payload.stage = stage;
            const updated = await ApplicationService.addEvent(application.id, payload);
            setNote("");
            onChanged(updated);
        } catch (submitError) {
            setError(submitError.status === 409 ? "La candidatura è stata aggiornata altrove. Ricarica e riprova." : submitError.message);
        } finally {
            setBusy(false);
        }
    };

    return (
        <aside className="application-detail" aria-labelledby="application-detail-title">
            <header><div><span className={`stage-badge stage-badge--${application.current_stage}`}>{STAGE_LABELS[application.current_stage]}</span><h2 id="application-detail-title">{snapshot.title || "Candidatura"}</h2><p>{snapshot.company}{snapshot.location ? ` · ${snapshot.location}` : ""}</p></div><button type="button" className="icon-button" onClick={onClose} aria-label="Chiudi dettaglio"><i className="bi bi-x-lg" /></button></header>
            <div className="application-snapshot"><div><i className="bi bi-camera" /><span><strong>Snapshot locale</strong><small>Annuncio fissato alla creazione della candidatura</small></span></div>{url && <a className="button button--secondary" href={url} target="_blank" rel="noopener noreferrer">Apri sorgente <i className="bi bi-box-arrow-up-right" /></a>}</div>
            {error && <div className="inline-alert inline-alert--danger" role="alert">{error}</div>}
            <form className="application-event-form" onSubmit={submit}>
                <h3>Aggiungi al diario</h3>
                <div className="form-grid form-grid--2">
                    <label className="field-stack"><span>Tipo evento</span><select className="form-select" value={eventType} onChange={(e) => { setEventType(e.target.value); if (e.target.value === "stage") setStage(TRANSITIONS[application.current_stage][0] || ""); }}>{Object.entries(EVENT_LABELS).filter(([value]) => value !== "stage" || TRANSITIONS[application.current_stage].length).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                    {eventType === "stage" && <label className="field-stack"><span>Nuova fase</span><select className="form-select" value={stage} onChange={(e) => setStage(e.target.value)}>{TRANSITIONS[application.current_stage].map((value) => <option key={value} value={value}>{STAGE_LABELS[value]}</option>)}</select></label>}
                </div>
                <label className="field-stack"><span>{eventType === "task" ? "Attività" : "Nota"}</span><textarea className="form-control" rows="3" value={note} onChange={(e) => setNote(e.target.value)} required={["note", "contact", "interview"].includes(eventType)} placeholder="Dettagli, persone, prossima azione…" /></label>
                <button className="button button--primary" disabled={busy || (eventType === "stage" && !stage)}>{busy ? "Registro…" : "Registra evento"}</button>
            </form>
            <section className="application-timeline" aria-labelledby="timeline-title"><h3 id="timeline-title">Diario verificabile</h3>{[...application.events].reverse().map((entry) => <article key={entry.id}><span className="timeline-dot" /><div><header><strong>{entry.event_type === "stage" ? STAGE_LABELS[entry.stage] : EVENT_LABELS[entry.event_type]}</strong><time dateTime={entry.occurred_at}>{new Date(entry.occurred_at).toLocaleString("it-IT")}</time></header>{entry.note && <p>{entry.note}</p>}</div></article>)}</section>
        </aside>
    );
}

