import { useState } from "react";
import { saveBlob } from "../../lib/download";
import { ApplicationService } from "../../services/applications";
import { useI18n } from "../../i18n/useI18n";

function asIso(value) {
    return value ? new Date(value).toISOString() : null;
}

export function ApplicationTasks({ application, onChanged }) {
    const { language, t } = useI18n();
    const locale = language === "it" ? "it-IT" : "en-GB";
    const [title, setTitle] = useState("");
    const [dueAt, setDueAt] = useState("");
    const [reminderMinutes, setReminderMinutes] = useState("none");
    const [priority, setPriority] = useState("normal");
    const [busy, setBusy] = useState("");
    const [error, setError] = useState("");
    const tasks = application.tasks || [];
    const hasCalendarTasks = tasks.some((task) => task.status === "pending" && task.due_at);

    const create = async (event) => {
        event.preventDefault();
        setBusy("create");
        setError("");
        try {
            const due = asIso(dueAt);
            const reminder = due && reminderMinutes !== "none"
                ? new Date(new Date(due).getTime() - Number(reminderMinutes) * 60_000).toISOString()
                : null;
            const updated = await ApplicationService.createTask(application.id, {
                expected_revision: application.revision,
                title: title.trim(),
                due_at: due,
                reminder_at: reminder,
                priority,
            });
            setTitle("");
            setDueAt("");
            setReminderMinutes("none");
            setPriority("normal");
            onChanged(updated);
        } catch (taskError) {
            setError(taskError.status === 409 ? t("applicationDetail.conflict") : taskError.message);
        } finally {
            setBusy("");
        }
    };

    const changeStatus = async (task, status) => {
        setBusy(task.id);
        setError("");
        try {
            onChanged(await ApplicationService.updateTask(application.id, task.id, {
                expected_revision: application.revision,
                status,
            }));
        } catch (taskError) {
            setError(taskError.status === 409 ? t("applicationDetail.conflict") : taskError.message);
        } finally {
            setBusy("");
        }
    };

    const downloadCalendar = async () => {
        setBusy("calendar");
        setError("");
        try {
            saveBlob(await ApplicationService.downloadTaskCalendar(application.id));
        } catch (calendarError) {
            setError(calendarError.message);
        } finally {
            setBusy("");
        }
    };

    return (
        <section className="application-operations" aria-labelledby="application-tasks-title">
            <header>
                <div><span>{t("tasks.kicker")}</span><h3 id="application-tasks-title">{t("tasks.title")}</h3></div>
                <button type="button" className="button button--secondary" disabled={!hasCalendarTasks || Boolean(busy)} onClick={downloadCalendar}><i className="bi bi-calendar3" /> {t("tasks.calendar")}</button>
            </header>
            <p>{t("tasks.copy")}</p>
            {error && <div className="inline-alert inline-alert--danger" role="alert">{error}</div>}
            {tasks.length > 0 && <div className="application-task-list">{tasks.map((task) => (
                <article key={task.id} className={`application-task application-task--${task.status}`}>
                    <div><span className={`task-priority task-priority--${task.priority}`}>{t(`tasks.priority.${task.priority}`)}</span><strong>{task.title}</strong>{task.due_at && <time dateTime={task.due_at}>{new Date(task.due_at).toLocaleString(locale)}</time>}</div>
                    <div className="button-cluster">
                        {task.status === "pending" && <><button type="button" className="button button--secondary" disabled={Boolean(busy)} onClick={() => changeStatus(task, "completed")}><i className="bi bi-check-lg" /> {t("tasks.complete")}</button><button type="button" className="icon-button" disabled={Boolean(busy)} onClick={() => changeStatus(task, "cancelled")} aria-label={t("tasks.cancel", { title: task.title })}><i className="bi bi-x-lg" /></button></>}
                        {task.status !== "pending" && <button type="button" className="button button--secondary" disabled={Boolean(busy)} onClick={() => changeStatus(task, "pending")}><i className="bi bi-arrow-counterclockwise" /> {t("tasks.reopen")}</button>}
                    </div>
                </article>
            ))}</div>}
            <form className="application-task-form" onSubmit={create}>
                <label className="field-stack"><span>{t("tasks.action")}</span><input className="form-control" value={title} onChange={(event) => setTitle(event.target.value)} maxLength="500" required placeholder={t("tasks.actionPlaceholder")} /></label>
                <div className="form-grid form-grid--3">
                    <label className="field-stack"><span>{t("tasks.due")}</span><input className="form-control" type="datetime-local" value={dueAt} onChange={(event) => { setDueAt(event.target.value); if (!event.target.value) setReminderMinutes("none"); }} /></label>
                    <label className="field-stack"><span>{t("tasks.priority")}</span><select className="form-select" value={priority} onChange={(event) => setPriority(event.target.value)}>{["low", "normal", "high", "urgent"].map((value) => <option key={value} value={value}>{t(`tasks.priority.${value}`)}</option>)}</select></label>
                    <label className="field-stack"><span>{t("tasks.reminder")}</span><select className="form-select" value={reminderMinutes} disabled={!dueAt} onChange={(event) => setReminderMinutes(event.target.value)}><option value="none">{t("tasks.reminder.none")}</option><option value="30">{t("tasks.reminder.30")}</option><option value="60">{t("tasks.reminder.60")}</option><option value="1440">{t("tasks.reminder.1440")}</option></select></label>
                </div>
                <button className="button button--primary" disabled={Boolean(busy)}>{busy === "create" ? t("tasks.adding") : t("tasks.add")}</button>
            </form>
        </section>
    );
}
