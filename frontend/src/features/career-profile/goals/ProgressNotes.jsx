import { useState } from "react";

export function ProgressNotes({ notes = [], onChange }) {
    const [draft, setDraft] = useState("");
    const add = () => {
        const text = draft.trim();
        if (!text) return;
        onChange([...notes, { recorded_at: new Date().toISOString(), text }]);
        setDraft("");
    };
    const update = (index, text) => onChange(notes.map((note, position) => position === index ? { ...note, text } : note));
    const remove = (index) => onChange(notes.filter((_, position) => position !== index));
    return (
        <section className="goal-subsection progress-notes" aria-label="Diario avanzamento obiettivo">
            <div className="goal-subsection__heading"><strong>Diario di avanzamento</strong><span>{notes.length} note</span></div>
            <div className="progress-notes__composer">
                <label className="field-stack"><span>Nuova nota di avanzamento</span><textarea className="form-control" rows="2" maxLength="2000" value={draft} onChange={(event) => setDraft(event.target.value)} /></label>
                <button type="button" className="button button--ghost" onClick={add} disabled={!draft.trim()}>Aggiungi nota di avanzamento</button>
            </div>
            {notes.map((note, index) => <article className="progress-note" key={`${note.recorded_at}-${index}`}><time dateTime={note.recorded_at}>{new Date(note.recorded_at).toLocaleString("it-IT")}</time><label className="field-stack"><span>Nota avanzamento {index + 1}</span><textarea className="form-control" rows="2" maxLength="2000" value={note.text} onChange={(event) => update(index, event.target.value)} /></label><button type="button" className="icon-button icon-button--danger" onClick={() => remove(index)} aria-label={`Rimuovi nota avanzamento ${index + 1}`}><i className="bi bi-trash3" /></button></article>)}
        </section>
    );
}
