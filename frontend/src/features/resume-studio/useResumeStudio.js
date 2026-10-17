import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../lib/client";
import { CareerService } from "../../services/career";
import { ResumeService } from "../../services/resumes";
import { useToast } from "../../context/ToastContext";
import { useI18n } from "../../i18n/useI18n";
import { newResumeDraft, resumeWritePayload } from "./resumeModel";
import { loadResumeWorkspace, mergeResumeResponse } from "./resumeWorkspace";
import { useResumeOperations } from "./useResumeOperations";

function localizedError(messageKey) {
    const error = new Error(messageKey);
    error.messageKey = messageKey;
    return error;
}

function errorMessage(error) {
    return error?.messageKey
        ? { messageKey: error.messageKey, variables: error.variables }
        : { message: error?.message || String(error) };
}

export function useResumeStudio({ requestedResumeId = null } = {}) {
    const { showToast } = useToast();
    const { t } = useI18n();
    const [profile, setProfile] = useState(null);
    const [resumes, setResumes] = useState([]);
    const [draft, setDraft] = useState(null);
    const [dirty, setDirty] = useState(false);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState("");
    const [error, setError] = useState(null);
    const [profileMissing, setProfileMissing] = useState(false);
    const [targetUnavailable, setTargetUnavailable] = useState(false);
    const [generationGoalId, setGenerationGoalId] = useState("");
    const [syncPreview, setSyncPreview] = useState(null);
    const [syncSelection, setSyncSelection] = useState([]);
    const [versionName, setVersionName] = useState(() => t("resume.defaultVersionName"));
    const [versionComparison, setVersionComparison] = useState(null);
    const [autosaveState, setAutosaveState] = useState("idle");
    const changeSequence = useRef(0);
    const fieldSequences = useRef(new Map());
    const { invalidate, run } = useResumeOperations({ setBusy, setError, errorMessage });
    const translatorRef = useRef(t);
    useEffect(() => { translatorRef.current = t; }, [t]);
    const freshDraft = useCallback((facts) => ({
        ...newResumeDraft(facts),
        title: translatorRef.current("resume.defaultDraftTitle"),
    }), []);

    const installDraft = useCallback((response) => {
        setDraft(response);
        setDirty(false);
        setSyncPreview(null);
        setVersionComparison(null);
        setAutosaveState("idle");
    }, []);

    const loadDraft = useCallback((id) => {
        invalidate();
        setLoading(false);
        return run("load", async (request) => {
            const response = await ResumeService.get(id, request.options);
            if (request.isCurrent()) installDraft(response);
        });
    }, [installDraft, invalidate, run]);

    const requestInitialization = useCallback(() => {
        invalidate();
        return run("load", async (request) => {
            const result = await loadResumeWorkspace({
                requestedResumeId, freshDraft, signal: request.signal,
            });
            if (!request.isCurrent()) return;
            if (result.profileError) {
                if (result.profileError instanceof ApiError && result.profileError.status === 404) {
                    setProfileMissing(true);
                } else {
                    setError(errorMessage(result.profileError));
                }
            } else {
                setProfile(result.profile);
                setResumes(result.resumes);
                setGenerationGoalId(result.profile.goals?.find((goal) => goal.is_primary)?.id || result.profile.goals?.[0]?.id || "");
                setProfileMissing(false);
                setTargetUnavailable(Boolean(result.targetUnavailable));
                installDraft(result.draft);
                setError(null);
            }
            setLoading(false);
        }, (loadError) => {
            setError(errorMessage(loadError));
            setLoading(false);
        });
    }, [freshDraft, installDraft, invalidate, requestedResumeId, run]);

    const initialize = useCallback(() => {
        setLoading(true);
        setProfileMissing(false);
        setTargetUnavailable(false);
        return requestInitialization();
    }, [requestInitialization]);

    useEffect(() => {
        void requestInitialization();
    }, [requestInitialization]);

    const refreshList = useCallback(async (request) => {
        const response = await ResumeService.list(request.options);
        if (request.isCurrent()) setResumes(response);
    }, []);
    const changeDraft = (patch) => {
        changeSequence.current += 1;
        for (const field of Object.keys(patch)) fieldSequences.current.set(field, changeSequence.current);
        setDraft((current) => ({ ...current, ...patch }));
        setDirty(true);
        setAutosaveState("pending");
    };
    const startNew = () => {
        invalidate();
        setLoading(false);
        installDraft(freshDraft(profile.facts));
        setVersionName(t("resume.defaultVersionName"));
    };

    const applySavedResponse = useCallback((response, sequence, request) => {
        if (!request.isCurrent()) return;
        const unchanged = changeSequence.current === sequence;
        const editedFields = new Set([...fieldSequences.current]
            .filter(([, changedAt]) => changedAt > sequence).map(([field]) => field));
        setDraft((current) => request.isCurrent()
            ? unchanged ? response : mergeResumeResponse(current, response, editedFields)
            : current);
        setDirty(!unchanged);
        setAutosaveState(unchanged ? "idle" : "pending");
    }, []);

    const persist = async (request, sequence) => {
        if (!draft.title.trim()) throw localizedError("resume.errorTitle");
        if (!draft.selected_fact_ids.length) throw localizedError("resume.errorFacts");
        if (draft.template_kind === "photo" && !draft.photo_asset_id) throw localizedError("resume.errorPhoto");
        if (draft.id && !dirty) return draft;
        const response = draft.id
            ? await ResumeService.update(draft.id, resumeWritePayload(draft), request.options)
            : await ResumeService.create(resumeWritePayload(draft), request.options);
        if (!request.isCurrent()) return null;
        applySavedResponse(response, sequence, request);
        await refreshList(request);
        return response;
    };

    const save = async () => {
        const sequence = changeSequence.current;
        return run("save", async (request) => {
            await persist(request, sequence);
            if (request.isCurrent()) showToast({ messageKey: "resume.savedToast" }, "success");
        });
    };
    const publish = async () => {
        const sequence = changeSequence.current;
        return run("publish", async (request) => {
            const saved = await persist(request, sequence);
            if (!request.isCurrent()) return;
            if (!versionName.trim()) throw localizedError("resume.errorVersion");
            await ResumeService.publish(saved.id, versionName.trim(), request.options);
            if (!request.isCurrent()) return;
            const response = await ResumeService.get(saved.id, request.options);
            if (!request.isCurrent()) return;
            applySavedResponse(response, sequence, request);
            setVersionName(t("resume.nextNamedVersion", { title: saved.title }));
            await refreshList(request);
            if (request.isCurrent()) showToast({ messageKey: "resume.publishedToast" }, "success");
        });
    };
    const generateFromProfile = async () => {
        const sequence = changeSequence.current;
        return run("generate", async (request) => {
            const response = await ResumeService.generate({
                title: draft.title.trim() || t("resume.defaultDraftTitle"),
                template_kind: draft.template_kind,
                career_goal_id: generationGoalId || null,
                photo_asset_id: draft.template_kind === "photo" ? draft.photo_asset_id : null,
            }, request.options);
            if (!request.isCurrent()) return;
            applySavedResponse(response, sequence, request);
            setVersionComparison(null);
            await refreshList(request);
            if (request.isCurrent()) showToast({ messageKey: "resume.generatedToast" }, "success");
        });
    };
    const duplicate = async () => {
        const sequence = changeSequence.current;
        return run("duplicate", async (request) => {
            if (!draft.id) return;
            const response = await ResumeService.duplicate(draft.id, { title: t("resume.duplicateTitle", { title: draft.title }) }, request.options);
            if (!request.isCurrent()) return;
            applySavedResponse(response, sequence, request);
            setSyncPreview(null);
            await refreshList(request);
            if (request.isCurrent()) showToast({ messageKey: "resume.duplicatedToast" }, "success");
        });
    };
    const promoteClaim = async (blockId) => {
        const sequence = changeSequence.current;
        return run("promote-claim", async (request) => {
            const saved = await persist(request, sequence);
            if (!request.isCurrent()) return;
            const response = await ResumeService.promoteClaim(saved.id, {
                expected_revision: saved.revision,
                expected_profile_revision: profile.revision,
                block_id: blockId,
            }, request.options);
            if (!request.isCurrent()) return;
            const refreshedProfile = await CareerService.getProfile({ signal: request.signal, suppressGlobalError: true });
            if (!request.isCurrent()) return;
            setProfile(refreshedProfile);
            applySavedResponse(response, sequence, request);
            await refreshList(request);
            if (request.isCurrent()) showToast({ messageKey: "resume.promotedToast" }, "success");
        });
    };
    const reviewSync = async () => {
        const sequence = changeSequence.current;
        return run("sync-preview", async (request) => {
            const response = await ResumeService.sync(draft.id, { expected_revision: draft.revision, mode: "preview", sections: [] }, request.options);
            if (!request.isCurrent() || sequence !== changeSequence.current) return;
            setSyncPreview(response);
            setSyncSelection([]);
        });
    };
    const applySync = async (mode = "apply") => {
        if (mode === "reset" && !window.confirm(t("resume.resetConfirm"))) return;
        const sequence = changeSequence.current;
        await run("sync", async (request) => {
            const response = await ResumeService.sync(draft.id, { expected_revision: draft.revision, mode, sections: mode === "apply" ? syncSelection : [] }, request.options);
            if (!request.isCurrent()) return;
            applySavedResponse(response.draft, sequence, request);
            setSyncPreview(null);
            await refreshList(request);
            if (request.isCurrent()) showToast({ messageKey: mode === "reset" ? "resume.resetToast" : "resume.syncToast" }, "success");
        });
    };
    const uploadPhoto = async (file) => {
        if (!file) return;
        await run("photo", async (request) => {
            const asset = await CareerService.uploadPhoto(file, request.options);
            if (!request.isCurrent()) return;
            changeDraft({ photo_asset_id: asset.id });
            showToast({ messageKey: "resume.photoToast" }, "success");
        });
    };
    const remove = async () => {
        if (!draft.id || !window.confirm(t("resume.removeConfirm", { title: draft.title }))) return;
        const sequence = changeSequence.current;
        await run("delete", async (request) => {
            await ResumeService.remove(draft.id, request.options);
            if (!request.isCurrent()) return;
            const next = await ResumeService.list(request.options);
            if (!request.isCurrent()) return;
            const response = next.length
                ? await ResumeService.get(next[0].id, request.options)
                : freshDraft(profile.facts);
            if (!request.isCurrent()) return;
            setResumes(next);
            if (sequence === changeSequence.current) installDraft(response);
            else {
                // Keep edits made after deletion started as a new unsaved draft.
                setDraft((current) => request.isCurrent()
                    ? { ...current, id: null, revision: null, versions: [] } : current);
                setDirty(true);
                setAutosaveState("pending");
            }
        });
    };
    const compareVersions = async (versionIds) => run("compare-versions", async (request) => {
        if (versionIds.length !== 2) return;
        const response = await ResumeService.compareVersions(versionIds[0], versionIds[1], request.options);
        if (request.isCurrent()) setVersionComparison(response);
    });
    const restoreVersion = async (version) => {
        if (!window.confirm(t("resume.restoreConfirm", { title: version.name }))) return;
        const sequence = changeSequence.current;
        await run("restore-version", async (request) => {
            const response = await ResumeService.restoreVersion(draft.id, version.id, draft.revision, request.options);
            if (!request.isCurrent()) return;
            applySavedResponse(response, sequence, request);
            setVersionComparison(null);
            await refreshList(request);
            if (request.isCurrent()) showToast({ messageKey: "resume.restoredToast" }, "success");
        });
    };

    useEffect(() => {
        if (!dirty || !draft || busy) return undefined;
        if (!draft.title.trim() || !draft.selected_fact_ids.length) return undefined;
        if (draft.template_kind === "photo" && !draft.photo_asset_id) return undefined;
        const timer = window.setTimeout(() => {
            const sequence = changeSequence.current;
            void run("autosave", async (request) => {
                setAutosaveState("saving");
                const response = draft.id
                    ? await ResumeService.update(draft.id, resumeWritePayload(draft), request.options)
                    : await ResumeService.create(resumeWritePayload(draft), request.options);
                if (!request.isCurrent()) return;
                applySavedResponse(response, sequence, request);
                await refreshList(request);
                if (request.isCurrent()) setAutosaveState(changeSequence.current === sequence ? "saved" : "pending");
            }, (autosaveError) => {
                setAutosaveState("error");
                setError({
                    messageKey: "resume.autosaveFailed",
                    variables: { message: autosaveError.message || { messageKey: "common.unknownError" } },
                });
            });
        }, 1_000);
        return () => window.clearTimeout(timer);
    }, [applySavedResponse, busy, dirty, draft, refreshList, run]);

    return { profile, resumes, draft, dirty, loading, busy, error, profileMissing, targetUnavailable, generationGoalId, syncPreview, syncSelection, versionName, versionComparison, autosaveState, initialize, loadDraft, changeDraft, startNew, save, publish, generateFromProfile, duplicate, promoteClaim, reviewSync, applySync, uploadPhoto, remove, compareVersions, restoreVersion, setGenerationGoalId, setSyncSelection, setVersionName, closeSync: () => setSyncPreview(null), setError };
}
