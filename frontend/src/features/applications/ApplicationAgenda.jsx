import { useCallback, useEffect, useState } from "react";
import { ApplicationService } from "../../services/applications";
import { useI18n } from "../../i18n/useI18n";
import { nextAgendaRefreshDelay, nextLocalDayEnd } from "./agendaTime";

const STATE_KEYS = {
    overdue: "agenda.state.overdue",
    today: "agenda.state.today",
    upcoming: "agenda.state.upcoming",
    unscheduled: "agenda.state.unscheduled",
    needs_action: "agenda.state.needsAction",
};

export function ApplicationAgenda({
    onOpen,
    openingId = "",
    expandedId = "",
    refreshKey = 0,
}) {
    const { language, t } = useI18n();
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [requestRevision, setRequestRevision] = useState(0);
    const locale = language === "it" ? "it-IT" : "en-GB";
    const refresh = useCallback(() => {
        setRequestRevision((value) => value + 1);
    }, []);

    useEffect(() => {
        const controller = new AbortController();
        ApplicationService.agenda(
            {
                localDayEnd: nextLocalDayEnd().toISOString(),
                horizonDays: 7,
                limit: 12,
            },
            { signal: controller.signal, suppressGlobalError: true },
        )
            .then((response) => {
                if (!controller.signal.aborted) {
                    setData(response);
                    setError("");
                }
            })
            .catch((loadError) => {
                if (!controller.signal.aborted) setError(loadError.message);
            })
            .finally(() => {
                if (!controller.signal.aborted) setLoading(false);
            });
        return () => controller.abort();
    }, [refreshKey, requestRevision]);

    useEffect(() => {
        const handleFocus = () => refresh();
        const handleVisibility = () => {
            if (document.visibilityState === "visible") refresh();
        };
        window.addEventListener("focus", handleFocus);
        document.addEventListener("visibilitychange", handleVisibility);
        return () => {
            window.removeEventListener("focus", handleFocus);
            document.removeEventListener("visibilitychange", handleVisibility);
        };
    }, [refresh]);

    useEffect(() => {
        const delay = nextAgendaRefreshDelay(data);
        if (delay === null) return undefined;
        const timer = window.setTimeout(refresh, delay);
        return () => window.clearTimeout(timer);
    }, [data, refresh]);

    const dateFormatter = new Intl.DateTimeFormat(locale, {
        weekday: "short",
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
    });

    return (
        <section className="surface-section application-agenda" aria-labelledby="application-agenda-title" aria-describedby="application-agenda-description">
            <div className="section-heading">
                <div>
                    <span className="section-kicker">{t("agenda.kicker")}</span>
                    <h2 id="application-agenda-title">{t("agenda.title")}</h2>
                    <p id="application-agenda-description">{t("agenda.description")}</p>
                </div>
                {data && <strong className="application-agenda__count">{data.visible_count}</strong>}
            </div>
            {loading && <div className="application-agenda__status" role="status"><span className="spinner-border spinner-border-sm" /> {t("agenda.loading")}</div>}
            {!loading && error && <div className="inline-alert inline-alert--warning" role="alert"><span>{t("agenda.error")}</span><button type="button" className="button button--secondary" onClick={() => { setLoading(true); setError(""); refresh(); }}>{t("agenda.retry")}</button></div>}
            {!loading && !error && data?.active_count === 0 && <div className="application-agenda__empty"><strong>{t("agenda.emptyTitle")}</strong><p>{t("agenda.emptyCopy")}</p></div>}
            {!loading && !error && data?.items?.length > 0 && <div className="application-agenda__list">
                {data.items.map((item) => {
                    const action = item.next_action;
                    return <button
                        key={item.application_id}
                        type="button"
                        className="application-agenda__item"
                        aria-label={t("agenda.open", { title: item.title, company: item.company })}
                        aria-haspopup="dialog"
                        aria-expanded={expandedId === item.application_id}
                        aria-busy={openingId === item.application_id || undefined}
                        disabled={openingId === item.application_id}
                        onClick={(event) => onOpen(item.application_id, event.currentTarget)}
                    >
                        <span className={`agenda-state agenda-state--${item.state}`}>{t(STATE_KEYS[item.state])}</span>
                        <span className="application-agenda__main"><strong>{action?.title || t("agenda.setAction")}</strong><small>{item.title} · {item.company}</small></span>
                        {action?.due_at ? <time dateTime={action.due_at}>{dateFormatter.format(new Date(action.due_at))}</time> : <span className="application-agenda__no-date">{t("agenda.noDate")}</span>}
                        <i className="bi bi-arrow-right" aria-hidden="true" />
                    </button>;
                })}
            </div>}
            {!loading && !error && data && (data.later_count > 0 || data.truncated_count > 0) && <p className="application-agenda__omissions">{data.later_count > 0 && t("agenda.later", { count: data.later_count })}{" "}{data.truncated_count > 0 && t("agenda.truncated", { count: data.truncated_count })}</p>}
        </section>
    );
}
