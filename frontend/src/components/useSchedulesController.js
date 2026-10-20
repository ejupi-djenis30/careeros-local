import { useCallback, useEffect, useRef, useState } from "react";
import { SearchService } from "../services/search";
import { useToast } from "../context/ToastContext";
import { reportUiFailure } from "../lib/uiDiagnostics";

function scheduleFields(profile) {
    return {
        schedule_enabled: profile.schedule_enabled,
        schedule_interval_hours: profile.schedule_interval_hours ?? 24,
    };
}

export function useSchedulesController() {
    const { showToast } = useToast();
    const [profiles, setProfiles] = useState([]);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState(null);
    const [refreshFailed, setRefreshFailed] = useState(false);
    const [pendingIds, setPendingIds] = useState(new Set());
    const owner = useRef({ mounted: false, generation: 0 });
    const read = useRef({ sequence: 0, controller: null });
    const loaded = useRef(false);
    const pending = useRef(new Map());

    const loadProfiles = useCallback(async () => {
        if (!owner.current.mounted) return false;
        const generation = owner.current.generation;
        const sequence = ++read.current.sequence;
        read.current.controller?.abort();
        const controller = new AbortController();
        read.current.controller = controller;
        const current = () => owner.current.mounted
            && owner.current.generation === generation
            && read.current.sequence === sequence && !controller.signal.aborted;
        if (!loaded.current) setLoading(true);
        setRefreshing(true);
        setError(null);
        setRefreshFailed(false);
        try {
            const data = await SearchService.getProfileSummaries({
                signal: controller.signal, suppressGlobalError: true,
            });
            if (!current()) return false;
            setProfiles(Array.isArray(data) ? data : []);
            loaded.current = true;
            return true;
        } catch (reason) {
            if (!current() || reason?.name === "AbortError") return false;
            reportUiFailure("schedules_profiles");
            if (loaded.current) {
                setRefreshFailed(true);
            } else {
                setError({ messageKey: "schedules.loadFailed" });
                showToast({ messageKey: "schedules.loadFailedRefresh" });
            }
            return false;
        } finally {
            if (current()) {
                read.current.controller = null;
                setLoading(false);
                setRefreshing(false);
            }
        }
    }, [showToast]);

    useEffect(() => {
        const lifecycle = owner.current;
        const reads = read.current;
        const writes = pending.current;
        lifecycle.mounted = true;
        lifecycle.generation += 1;
        const initial = window.setTimeout(() => {
            setPendingIds(new Set());
            void loadProfiles();
        }, 0);
        return () => {
            window.clearTimeout(initial);
            lifecycle.mounted = false;
            lifecycle.generation += 1;
            reads.sequence += 1;
            reads.controller?.abort();
            writes.clear();
        };
    }, [loadProfiles]);

    const mutate = useCallback(async (profileId, enabled, intervalHours, failureKey) => {
        if (!owner.current.mounted || pending.current.has(profileId)) return false;
        const generation = owner.current.generation;
        const token = {};
        pending.current.set(profileId, token);
        setPendingIds(new Set(pending.current.keys()));
        const current = () => owner.current.mounted
            && owner.current.generation === generation
            && pending.current.get(profileId) === token;
        try {
            const ack = await SearchService.toggleSchedule(profileId, enabled, intervalHours, {
                suppressGlobalError: true,
            });
            if (!current()) return false;
            if (ack?.id !== profileId || typeof ack.schedule_enabled !== "boolean"
                || (ack.schedule_interval_hours !== null && (!Number.isInteger(ack.schedule_interval_hours)
                    || ack.schedule_interval_hours < 1))) {
                throw new Error();
            }
            const fields = scheduleFields(ack);
            setProfiles((known) => known.map((profile) => profile.id === profileId
                ? { ...profile, ...fields } : profile));
            void loadProfiles();
            return true;
        } catch (reason) {
            if (current()) {
                showToast({
                    messageKey: failureKey,
                    variables: { error: reason?.message || { messageKey: "common.unknownError" } },
                });
            }
            return false;
        } finally {
            if (current()) {
                pending.current.delete(profileId);
                setPendingIds(new Set(pending.current.keys()));
            }
        }
    }, [loadProfiles, showToast]);

    return {
        profiles, loading, refreshing, error, refreshFailed, pendingIds,
        refreshProfiles: loadProfiles,
        toggle: (id, enabled, interval) => mutate(id, !enabled, interval, "schedules.toggleFailed"),
        remove: (id) => mutate(id, false, null, "schedules.removeFailed"),
        changeInterval: (id, interval) => mutate(id, true, parseInt(interval, 10), "schedules.intervalFailed"),
    };
}
