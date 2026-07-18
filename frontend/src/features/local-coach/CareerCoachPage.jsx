import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../../lib/client";
import { CareerService } from "../../services/career";
import { CoachService } from "../../services/coach";
import { useLocalModelStatus } from "../local-model/useLocalModelStatus";
import { FACT_LABELS, factTitle } from "../career-profile/profileModel";

function ConversationList({ conversations, activeId, onSelect, onNew, onDelete }) {
    return <aside className="coach-conversations"><button type="button" className="button button--primary" onClick={onNew}><i className="bi bi-plus-lg" /> Nuova conversazione</button><div>{conversations.map((conversation) => <div key={conversation.id} className={`conversation-row ${activeId === conversation.id ? "is-active" : ""}`}><button type="button" onClick={() => onSelect(conversation.id)}><strong>{conversation.title}</strong><span>{conversation.message_count} messaggi · {new Date(conversation.updated_at).toLocaleDateString("it-IT")}</span></button><button type="button" className="icon-button" onClick={() => onDelete(conversation)} aria-label={`Elimina ${conversation.title}`}><i className="bi bi-trash3" /></button></div>)}</div>{conversations.length === 0 && <p className="coach-conversations__empty">Le conversazioni vengono salvate solo nel database locale.</p>}</aside>;
}

function ContextPicker({ facts, selectedIds, onChange, jobIds, onJobIds }) {
    const selected = new Set(selectedIds);
    const toggle = (id) => onChange(selected.has(id) ? selectedIds.filter((item) => item !== id) : [...selectedIds, id]);
    return <details className="coach-context"><summary><span><i className="bi bi-paperclip" /> Contesto esplicito</span><strong>{selectedIds.length} fatti</strong></summary><div><p>Solo gli elementi selezionati entrano nel prompt locale. Email e telefono non vengono inclusi.</p><div className="coach-context__facts">{facts.map((fact) => <label key={fact.id} className={selected.has(fact.id) ? "is-selected" : ""}><input type="checkbox" checked={selected.has(fact.id)} onChange={() => toggle(fact.id)} /><span><small>{FACT_LABELS[fact.fact_type]}</small><strong>{factTitle(fact)}</strong></span></label>)}</div><label className="field-stack"><span>ID annunci · separati da virgola</span><input className="form-control" value={jobIds} onChange={(e) => onJobIds(e.target.value)} placeholder="12, 18" /></label></div></details>;
}

function Message({ message }) {
    return <article className={`coach-message coach-message--${message.role}`}><div className="coach-message__avatar"><i className={`bi ${message.role === "assistant" ? "bi-cpu" : "bi-person"}`} /></div><div><header><strong>{message.role === "assistant" ? "Coach locale" : "Tu"}</strong><time dateTime={message.created_at}>{new Date(message.created_at).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}</time></header><p>{message.content}</p>{(message.cited_fact_ids?.length > 0 || message.cited_job_ids?.length > 0) && <footer><span>Fonti usate</span>{message.cited_fact_ids?.map((id) => <code key={id}>fatto {id.slice(0, 8)}</code>)}{message.cited_job_ids?.map((id) => <code key={id}>annuncio #{id}</code>)}</footer>}</div></article>;
}

export function CareerCoachPage() {
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
            setError(sendError.status === 503 ? "Il modello locale non è disponibile. Controlla o riavvia il runtime dalla schermata Oggi." : sendError.message);
            refreshModel();
        } finally {
            setSending(false);
        }
    };

    const removeConversation = async (item) => {
        if (!window.confirm(`Eliminare definitivamente “${item.title}” dal database locale?`)) return;
        try {
            await CoachService.deleteConversation(item.id);
            if (conversation?.id === item.id) setConversation(null);
            await refreshConversations();
        } catch (deleteError) { setError(deleteError.message); }
    };

    if (loading) return <div className="page-loader" role="status"><span className="spinner-border" /><span>Carico il coach locale…</span></div>;
    if (profileMissing) return <div className="state-panel"><i className="bi bi-person-vcard" /><h2>Il coach ha bisogno del Career Vault</h2><p>Le risposte vengono fondate solo sui fatti che scegli.</p><Link className="button button--primary" to="/profile">Crea il profilo</Link></div>;

    return (
        <div className="coach-workspace">
            <ConversationList conversations={conversations} activeId={conversation?.id} onSelect={openConversation} onNew={() => { setConversation(null); setMessage(""); }} onDelete={removeConversation} />
            <section className="coach-panel">
                <header className="coach-panel__header"><div><span className={`model-dot ${modelStatus.ready ? "is-ready" : ""}`} /><div><strong>{conversation?.title || "Nuova conversazione"}</strong><span>{modelStatus.ready ? `${modelStatus.configured_model} · inferenza locale` : "Modello non pronto"}</span></div></div><span className="privacy-chip"><i className="bi bi-incognito" /> contesto selettivo</span></header>
                {!modelStatus.loading && !modelStatus.ready && <div className="model-setup" role="status"><i className="bi bi-cpu" /><div><strong>Completa il runtime locale</strong><p>Installa il modello verificato direttamente dall’app. Non servono terminale, account o chiavi API.</p></div><Link className="button button--secondary" to="/">Configura modello</Link><button type="button" className="button button--ghost" onClick={refreshModel}>Ricontrolla</button></div>}
                {error && <div className="inline-alert inline-alert--danger" role="alert">{error}</div>}
                <ContextPicker facts={profile?.facts || []} selectedIds={selectedFactIds} onChange={setSelectedFactIds} jobIds={jobIds} onJobIds={setJobIds} />
                <div className="coach-messages" aria-live="polite">{conversation?.messages?.length ? conversation.messages.map((entry) => <Message key={entry.id} message={entry} />) : <div className="coach-empty"><span className="coach-empty__mark">C</span><h2>Un coach che conosce solo ciò che autorizzi</h2><p>Chiedi una revisione del posizionamento, una strategia per un colloquio o un confronto tra il tuo profilo e uno degli annunci locali.</p><div><button type="button" onClick={() => setMessage("Quali sono i punti più forti del mio profilo e come posso dimostrarli?")}>Identifica i miei punti forti</button><button type="button" onClick={() => setMessage("Aiutami a preparare una risposta concreta alla domanda: parlami di te.")}>Prepara “parlami di te”</button></div></div>}</div>
                <form className="coach-composer" onSubmit={send}><label htmlFor="coach-message" className="visually-hidden">Messaggio al coach locale</label><textarea id="coach-message" rows="3" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Scrivi una domanda sulla tua carriera…" maxLength={20000} /><div><span><i className="bi bi-shield-lock" /> Nessun servizio cloud</span><button className="button button--primary" disabled={sending || !message.trim() || !modelStatus.ready}>{sending ? "Ragiono localmente…" : "Invia"} <i className="bi bi-arrow-up" /></button></div></form>
            </section>
        </div>
    );
}
