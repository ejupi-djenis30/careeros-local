import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../../lib/client";
import { CareerService } from "../../services/career";
import { CoachService } from "../../services/coach";
import { useLocalModelStatus } from "../local-model/useLocalModelStatus";
import { describeLocalAnalysisError } from "../local-model/localAnalysisError";

const requestOptions = (controller) => ({ signal: controller.signal, suppressGlobalError: true });

export function useCareerCoach(t) {
    const { status: modelStatus, refresh: refreshModel } = useLocalModelStatus();
    const [profile, setProfile] = useState(null);
    const [conversations, setConversations] = useState([]);
    const [conversation, setConversation] = useState(null);
    const [activeId, setActiveId] = useState(null);
    const [selectedFactIds, setSelectedFactIds] = useState([]);
    const [jobIds, setJobIds] = useState("");
    const [message, setComposer] = useState("");
    const [loading, setLoading] = useState(true);
    const [opening, setOpening] = useState(false);
    const [sending, setSending] = useState(false);
    const [deleting, setDeleting] = useState("");
    const [error, setError] = useState("");
    const [readFailure, setReadFailure] = useState("");
    const [profileMissing, setProfileMissing] = useState(false);
    const owner = useRef({ mounted: true, selection: 0, activeId: null, initial: null, load: null, send: null, remove: null, catalog: 0 });
    const composerSequence = useRef(0);
    const translator = useRef(t);
    useEffect(() => { translator.current = t; }, [t]);

    const setMessage = useCallback((value) => {
        composerSequence.current += 1;
        setComposer(value);
    }, []);
    const refreshConversations = useCallback(async (controller, current) => {
        const sequence = ++owner.current.catalog;
        const rows = await CoachService.listConversations(requestOptions(controller));
        if (current() && sequence === owner.current.catalog) setConversations(rows);
    }, []);
    const requestInitialization = useCallback(() => {
        owner.current.initial?.abort();
        const controller = new AbortController();
        owner.current.initial = controller;
        const current = () => owner.current.mounted && owner.current.initial === controller && !controller.signal.aborted;
        return Promise.all([
            CareerService.getProfile(requestOptions(controller)),
            CoachService.listConversations(requestOptions(controller)),
        ]).then(([loadedProfile, rows]) => {
            if (current()) { setProfile(loadedProfile); setConversations(rows); }
        }).catch((loadError) => {
            if (!current()) return;
            if (loadError instanceof ApiError && loadError.status === 404) setProfileMissing(true);
            else setError(loadError.message);
        }).finally(() => { if (current()) setLoading(false); });
    }, []);
    const initialize = () => {
        setLoading(true);
        setError("");
        setProfileMissing(false);
        return requestInitialization();
    };
    useEffect(() => {
        const state = owner.current;
        state.mounted = true;
        void requestInitialization();
        return () => {
            state.mounted = false;
            state.selection += 1;
            for (const controller of [state.initial, state.load, state.send, state.remove]) controller?.abort();
        };
    }, [requestInitialization]);

    const beginSelection = (id) => {
        const state = owner.current;
        state.selection += 1;
        state.load?.abort();
        state.send?.abort();
        state.load = null;
        state.send = null;
        state.activeId = id;
        setActiveId(id);
        setConversation(null);
        setSending(false);
        setOpening(false);
        setError("");
        setReadFailure("");
        return state.selection;
    };
    const openConversation = async (id) => {
        const selection = beginSelection(id);
        const controller = new AbortController();
        owner.current.load = controller;
        const current = () => owner.current.mounted && owner.current.selection === selection
            && owner.current.load === controller && !controller.signal.aborted;
        setOpening(true);
        try {
            const loaded = await CoachService.getConversation(id, requestOptions(controller));
            if (current()) setConversation(loaded);
        } catch (loadError) {
            if (current()) { setError(loadError.message); setReadFailure("conversation"); }
        } finally {
            if (current()) { setOpening(false); owner.current.load = null; }
        }
    };
    const newConversation = () => { beginSelection(null); setMessage(""); };
    const parsedJobIds = useMemo(() => jobIds.split(",").map((value) => Number(value.trim()))
        .filter((value) => Number.isInteger(value) && value > 0), [jobIds]);
    const canSend = Boolean(profile && modelStatus.ready && !opening && !sending
        && (!activeId || conversation?.id === activeId));

    const send = async (event) => {
        event.preventDefault();
        if (!canSend || !message.trim() || owner.current.send || owner.current.load) return;
        const controller = new AbortController();
        const selection = owner.current.selection;
        const sequence = composerSequence.current;
        owner.current.send = controller;
        const current = () => owner.current.mounted && owner.current.selection === selection
            && owner.current.send === controller && !controller.signal.aborted;
        let phase = "send";
        setSending(true);
        setError("");
        setReadFailure("");
        try {
            const reply = await CoachService.sendMessage({
                conversation_id: owner.current.activeId, message: message.trim(),
                fact_ids: [...selectedFactIds], job_ids: parsedJobIds,
            }, requestOptions(controller));
            if (!current()) return;
            owner.current.activeId = reply.conversation_id;
            setActiveId(reply.conversation_id);
            if (composerSequence.current === sequence) setMessage("");
            phase = "conversation";
            const loaded = await CoachService.getConversation(reply.conversation_id, requestOptions(controller));
            if (!current()) return;
            setConversation(loaded);
            phase = "catalog";
            await refreshConversations(controller, current);
        } catch (sendError) {
            if (!current()) return;
            if (phase === "send") {
                setError(describeLocalAnalysisError(sendError, translator.current)
                    || (sendError.status === 503 ? translator.current("coach.modelUnavailable") : sendError.message));
                refreshModel();
            } else { setError(sendError.message); setReadFailure(phase); }
        } finally {
            if (current()) { setSending(false); owner.current.send = null; }
        }
    };
    const retryRead = async () => {
        if (readFailure !== "catalog") return openConversation(owner.current.activeId);
        const selection = owner.current.selection;
        const controller = new AbortController();
        owner.current.load?.abort();
        owner.current.load = controller;
        const current = () => owner.current.mounted && owner.current.selection === selection
            && owner.current.load === controller && !controller.signal.aborted;
        setOpening(true);
        setError("");
        try {
            await refreshConversations(controller, current);
            if (current()) setReadFailure("");
        } catch (loadError) { if (current()) setError(loadError.message); }
        finally { if (current()) { setOpening(false); owner.current.load = null; } }
    };
    const removeConversation = async (item) => {
        if (owner.current.remove || !window.confirm(t("coach.deleteConfirm", { title: item.title }))) return;
        const controller = new AbortController();
        let selection = owner.current.selection;
        owner.current.remove = controller;
        const current = () => owner.current.mounted && !controller.signal.aborted;
        setDeleting(item.id);
        try {
            await CoachService.deleteConversation(item.id, requestOptions(controller));
            if (!current()) return;
            setConversations((rows) => rows.filter((row) => row.id !== item.id));
            if (owner.current.activeId === item.id) selection = beginSelection(null);
            await refreshConversations(controller, current);
        } catch (deleteError) {
            if (current() && owner.current.selection === selection) {
                setError(deleteError.message);
                setReadFailure("catalog");
            }
        } finally {
            if (owner.current.remove === controller) {
                owner.current.remove = null;
                if (current()) setDeleting("");
            }
        }
    };

    return { profile, conversations, conversation, activeId, selectedFactIds, setSelectedFactIds,
        jobIds, setJobIds, message, setMessage, loading, opening, sending, deleting, error, readFailure,
        profileMissing, modelStatus, refreshModel, canSend, initialize, openConversation, newConversation,
        send, retryRead, removeConversation };
}
