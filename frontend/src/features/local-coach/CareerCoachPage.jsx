import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../../lib/client";
import { CareerService } from "../../services/career";
import { CoachService } from "../../services/coach";
import { useLocalModelStatus } from "../local-model/useLocalModelStatus";
import { FACT_LABELS, factTitle } from "../career-profile/profileModel";
import { useI18n } from "../../i18n/useI18n";

function ConversationList({ conversations, activeId, onSelect, onNew, onDelete, locale, t }) {
    return <aside className="coach-conversations"><button type="button" className="button button--primary" onClick={onNew}><i className="bi bi-plus-lg" /> {t("coach.newConversation")}</button><div>{conversations.map((conversation) => <div key={conversation.id} className={`conversation-row ${activeId === conversation.id ? "is-active" : ""}`}><button type="button" onClick={() => onSelect(conversation.id)}><strong>{conversation.title}</strong><span>{t("coach.messages", { count: conversation.message_count })} · {new Date(conversation.updated_at).toLocaleDateString(locale)}</span></button><button type="button" className="icon-button" onClick={() => onDelete(conversation)} aria-label={t("coach.deleteConversation", { title: conversation.title })}><i className="bi bi-trash3" /></button></div>)}</div>{conversations.length === 0 && <p className="coach-conversations__empty">{t("coach.savedLocally")}</p>}</aside>;
}

function ContextPicker({ facts, selectedIds, onChange, jobIds, onJobIds, t }) {
    const selected = new Set(selectedIds);
    const toggle = (id) => onChange(selected.has(id) ? selectedIds.filter((item) => item !== id) : [...selectedIds, id]);
    return <details className="coach-context"><summary><span><i className="bi bi-paperclip" /> {t("coach.explicitContext")}</span><strong>{t("coach.factCount", { count: selectedIds.length })}</strong></summary><div><p>{t("coach.contextCopy")}</p><div className="coach-context__facts">{facts.map((fact) => <label key={fact.id} className={selected.has(fact.id) ? "is-selected" : ""}><input type="checkbox" checked={selected.has(fact.id)} onChange={() => toggle(fact.id)} /><span><small>{t(`fact.type.${fact.fact_type}`) || FACT_LABELS[fact.fact_type]}</small><strong>{factTitle(fact)}</strong></span></label>)}</div><label className="field-stack"><span>{t("coach.jobIds")}</span><input className="form-control" value={jobIds} onChange={(e) => onJobIds(e.target.value)} placeholder="12, 18" /></label></div></details>;
}

function Message({ message, locale, t }) {
    return <article className={`coach-message coach-message--${message.role}`}><div className="coach-message__avatar"><i className={`bi ${message.role === "assistant" ? "bi-cpu" : "bi-person"}`} /></div><div><header><strong>{message.role === "assistant" ? t("coach.local") : t("coach.you")}</strong><time dateTime={message.created_at}>{new Date(message.created_at).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" })}</time></header><p>{message.content}</p>{(message.cited_fact_ids?.length > 0 || message.cited_job_ids?.length > 0) && <footer><span>{t("coach.sources")}</span>{message.cited_fact_ids?.map((id) => <code key={id}>{t("coach.factSource", { id: id.slice(0, 8) })}</code>)}{message.cited_job_ids?.map((id) => <code key={id}>{t("coach.jobSource", { id })}</code>)}</footer>}</div></article>;
}

export function CareerCoachPage() {
    const { language, t } = useI18n();
    const locale = language === "it" ? "it-IT" : "en-GB";
    const { status: modelStatus, refresh: refreshModel } = useLocalModelStatus();
    const [profile, setProfile] = useState(null);
    const [conversations, setConversations] = useState([]);
    const [conversation, setConversation] = useState(null);
    const [selectedFactIds, setSelectedFactIds] = useState([]);
    const [jobIds, setJobIds] = useState("");
    const [message, setMessage] = useState("");
    const [loading, setLoading] = useState(true);
    const [sending, setSending] = useState(false);
    const [error, setError] = useState("");
    const [profileMissing, setProfileMissing] = useState(false);

    const refreshConversations = useCallback(async () => setConversations(await CoachService.listConversations()), []);
    useEffect(() => {
        Promise.all([CareerService.getProfile({ suppressGlobalError: true }), CoachService.listConversations()])
            .then(([loadedProfile, loadedConversations]) => { setProfile(loadedProfile); setConversations(loadedConversations); setSelectedFactIds([]); })
            .catch((loadError) => { if (loadError instanceof ApiError && loadError.status === 404) setProfileMissing(true); else setError(loadError.message); })
            .finally(() => setLoading(false));
    }, []);

    const openConversation = async (id) => {
        setError("");
        try { setConversation(await CoachService.getConversation(id)); } catch (loadError) { setError(loadError.message); }
    };

    const parsedJobIds = useMemo(() => jobIds.split(",").map((value) => Number(value.trim())).filter((value) => Number.isInteger(value) && value > 0), [jobIds]);

    const send = async (event) => {
        event.preventDefault();
        if (!message.trim() || !modelStatus.ready) return;
        setSending(true);
        setError("");
        try {
            const reply = await CoachService.sendMessage({ conversation_id: conversation?.id || null, message: message.trim(), fact_ids: selectedFactIds, job_ids: parsedJobIds });
            setMessage("");
            const loaded = await CoachService.getConversation(reply.conversation_id);
            setConversation(loaded);
            await refreshConversations();
        } catch (sendError) {
            setError(sendError.status === 503 ? t("coach.modelUnavailable") : sendError.message);
            refreshModel();
        } finally {
            setSending(false);
        }
    };

    const removeConversation = async (item) => {
        if (!window.confirm(t("coach.deleteConfirm", { title: item.title }))) return;
        try {
            await CoachService.deleteConversation(item.id);
            if (conversation?.id === item.id) setConversation(null);
            await refreshConversations();
        } catch (deleteError) { setError(deleteError.message); }
    };

    if (loading) return <div className="page-loader" role="status"><span className="spinner-border" /><span>{t("coach.loading")}</span></div>;
    if (profileMissing) return <div className="state-panel"><i className="bi bi-person-vcard" /><h2>{t("coach.needsVault")}</h2><p>{t("coach.needsVaultCopy")}</p><Link className="button button--primary" to="/profile">{t("coach.createProfile")}</Link></div>;

    return (
        <div className="coach-workspace">
            <ConversationList conversations={conversations} activeId={conversation?.id} onSelect={openConversation} onNew={() => { setConversation(null); setMessage(""); }} onDelete={removeConversation} locale={locale} t={t} />
            <section className="coach-panel">
                <header className="coach-panel__header"><div><span className={`model-dot ${modelStatus.ready ? "is-ready" : ""}`} /><div><strong>{conversation?.title || t("coach.newConversation")}</strong><span>{modelStatus.ready ? `${modelStatus.configured_model} · ${t("coach.inferenceLocal")}` : t("coach.modelNotReady")}</span></div></div><span className="privacy-chip"><i className="bi bi-incognito" /> {t("coach.selectiveContext")}</span></header>
                {!modelStatus.loading && !modelStatus.ready && <div className="model-setup" role="status"><i className="bi bi-cpu" /><div><strong>{t("coach.completeRuntime")}</strong><p>{t("coach.completeRuntimeCopy")}</p></div><Link className="button button--secondary" to="/">{t("coach.configureModel")}</Link><button type="button" className="button button--ghost" onClick={refreshModel}>{t("coach.recheck")}</button></div>}
                {error && <div className="inline-alert inline-alert--danger" role="alert">{error}</div>}
                <ContextPicker facts={profile?.facts || []} selectedIds={selectedFactIds} onChange={setSelectedFactIds} jobIds={jobIds} onJobIds={setJobIds} t={t} />
                <div className="coach-messages" aria-live="polite">{conversation?.messages?.length ? conversation.messages.map((entry) => <Message key={entry.id} message={entry} locale={locale} t={t} />) : <div className="coach-empty"><span className="coach-empty__mark">C</span><h2>{t("coach.emptyTitle")}</h2><p>{t("coach.emptyCopy")}</p><div><button type="button" onClick={() => setMessage(t("coach.suggestionStrengths"))}>{t("coach.suggestionStrengthsLabel")}</button><button type="button" onClick={() => setMessage(t("coach.suggestionIntro"))}>{t("coach.suggestionIntroLabel")}</button></div></div>}</div>
                <form className="coach-composer" onSubmit={send}><label htmlFor="coach-message" className="visually-hidden">{t("coach.messageLabel")}</label><textarea id="coach-message" rows="3" value={message} onChange={(e) => setMessage(e.target.value)} placeholder={t("coach.messagePlaceholder")} maxLength={20000} /><div><span><i className="bi bi-shield-lock" /> {t("coach.noCloud")}</span><button className="button button--primary" disabled={sending || !message.trim() || !modelStatus.ready}>{sending ? t("coach.thinking") : t("coach.send")} <i className="bi bi-arrow-up" /></button></div></form>
            </section>
        </div>
    );
}
