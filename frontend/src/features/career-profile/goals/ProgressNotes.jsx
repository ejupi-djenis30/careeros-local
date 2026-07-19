import { useState } from "react";
import { useI18n } from "../../../i18n/useI18n";

export function ProgressNotes({ notes = [], onChange }) {
    const { language, t } = useI18n();
    const locale = language === "it" ? "it-IT" : "en-GB";
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
        <section className="goal-subsection progress-notes" aria-label={t("goal.progressNotes")}>
            <div className="goal-subsection__heading"><strong>{t("goal.journal")}</strong><span>{t("goal.noteCount", { count: notes.length })}</span></div>
            <div className="progress-notes__composer">
                <label className="field-stack"><span>{t("goal.newNote")}</span><textarea className="form-control" rows="2" maxLength="2000" value={draft} onChange={(event) => setDraft(event.target.value)} /></label>
                <button type="button" className="button button--ghost" onClick={add} disabled={!draft.trim()}>{t("goal.addNote")}</button>
            </div>
            {notes.map((note, index) => <article className="progress-note" key={`${note.recorded_at}-${index}`}><time dateTime={note.recorded_at}>{new Date(note.recorded_at).toLocaleString(locale)}</time><label className="field-stack"><span>{t("goal.note", { index: index + 1 })}</span><textarea className="form-control" rows="2" maxLength="2000" value={note.text} onChange={(event) => update(index, event.target.value)} /></label><button type="button" className="icon-button icon-button--danger" onClick={() => remove(index)} aria-label={t("goal.removeNote", { index: index + 1 })}><i className="bi bi-trash3" /></button></article>)}
        </section>
    );
}
