import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../lib/client";
import { CareerService } from "../../services/career";
import { ResumeService } from "../../services/resumes";
import { useToast } from "../../context/ToastContext";
import { useI18n } from "../../i18n/useI18n";
import { newResumeDraft, resumeWritePayload } from "./resumeModel";

export function useResumeStudio() {
    const { showToast } = useToast();
    const { t } = useI18n();
    const [profile, setProfile] = useState(null);
    const [resumes, setResumes] = useState([]);
    const [draft, setDraft] = useState(null);
    const [dirty, setDirty] = useState(false);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState("");
    const [error, setError] = useState("");
    const [profileMissing, setProfileMissing] = useState(false);
    const [generationGoalId, setGenerationGoalId] = useState("");
    const [syncPreview, setSyncPreview] = useState(null);
    const [syncSelection, setSyncSelection] = useState([]);
    const [versionName, setVersionName] = useState(() => t("resume.defaultVersionName"));
    const [versionComparison, setVersionComparison] = useState(null);
    const [autosaveState, setAutosaveState] = useState("idle");
    const changeSequence = useRef(0);
    const autosaveInFlight = useRef(false);
    const initializationRequest = useRef({ controller: null, id: 0 });
    const translatorRef = useRef(t);
    useEffect(() => { translatorRef.current = t; }, [t]);
    const freshDraft = useCallback((facts) => ({
        ...newResumeDraft(facts),
        title: translatorRef.current("resume.defaultDraftTitle"),
    }), []);

    const loadDraft = useCallback(async (id) => {
        setBusy("load");
        setError("");
        try {
            setDraft(await ResumeService.get(id));
            setDirty(false);
            setSyncPreview(null);
            setVersionComparison(null);
        } catch (loadError) {
            setError(loadError.message);
        } finally {
            setBusy("");
        }
    }, []);

    const requestInitialization = useCallback(() => {
        const requestId = initializationRequest.current.id + 1;
        initializationRequest.current.controller?.abort();
        const controller = new AbortController();
        initializationRequest.current = { controller, id: requestId };
        const requestOptions = { signal: controller.signal };
        const profileRequest = Promise.resolve()
            .then(() => CareerService.getProfile({ ...requestOptions, suppressGlobalError: true }))
            .then((value) => ({ value }))
            .catch((requestError) => ({ error: requestError }));
        const resumesRequest = Promise.resolve().then(() => ResumeService.list(requestOptions));

        return Promise.all([profileRequest, resumesRequest])
            .then(([profileResult, loadedResumes]) => {
                if (profileResult.error) return { profileError: profileResult.error };
                const loadedProfile = profileResult.value;
                const draftRequest = loadedResumes.length
                    ? ResumeService.get(loadedResumes[0].id, requestOptions)
                    : Promise.resolve(freshDraft(loadedProfile.facts));
                return Promise.resolve(draftRequest).then((loadedDraft) => ({ loadedDraft, loadedProfile, loadedResumes }));
            })
            .then((result) => {
                if (controller.signal.aborted || initializationRequest.current.id !== requestId) return;
                if (result.profileError) {
                    if (result.profileError instanceof ApiError && result.profileError.status === 404) {
                        setProfileMissing(true);
                    } else {
                        setError(result.profileError.message);
                    }
                } else {
                    setProfile(result.loadedProfile);
                    setResumes(result.loadedResumes);
                    setGenerationGoalId(result.loadedProfile.goals?.find((goal) => goal.is_primary)?.id || result.loadedProfile.goals?.[0]?.id || "");
                    setProfileMissing(false);
                    setDraft(result.loadedDraft);
                    setError("");
                }
                setLoading(false);
                initializationRequest.current.controller = null;
            })
            .catch((loadError) => {
                if (controller.signal.aborted || initializationRequest.current.id !== requestId) return;
                setError(loadError.message);
                setLoading(false);
                initializationRequest.current.controller = null;
            });
    }, [freshDraft]);

    const initialize = useCallback(() => {
        setLoading(true);
        setError("");
        setProfileMissing(false);
        return requestInitialization();
    }, [requestInitialization]);

    useEffect(() => {
        void requestInitialization();
        return () => {
            initializationRequest.current.id += 1;
            initializationRequest.current.controller?.abort();
        };
    }, [requestInitialization]);
    const refreshList = async () => setResumes(await ResumeService.list());
    const changeDraft = (patch) => { changeSequence.current += 1; setDraft((current) => ({ ...current, ...patch })); setDirty(true); setAutosaveState("pending"); };
    const startNew = () => { changeSequence.current += 1; setDraft(freshDraft(profile.facts)); setDirty(false); setSyncPreview(null); setVersionComparison(null); setVersionName(t("resume.defaultVersionName")); setAutosaveState("idle"); };

    const applySavedResponse = (response, sequence) => {
        if (changeSequence.current === sequence) {
            setDraft(response);
            setDirty(false);
            return;
        }
        setDraft((current) => ({
            ...current,
            id: response.id,
            revision: response.revision,
            profile_revision: response.profile_revision,
            versions: response.versions,
        }));
    };

    const persist = async () => {
        if (!draft.title.trim()) throw new Error(t("resume.errorTitle"));
        if (!draft.selected_fact_ids.length) throw new Error(t("resume.errorFacts"));
        if (draft.template_kind === "photo" && !draft.photo_asset_id) throw new Error(t("resume.errorPhoto"));
        if (draft.id && !dirty) return draft;
        const sequence = changeSequence.current;
        const snapshot = draft;
        const response = snapshot.id
            ? await ResumeService.update(snapshot.id, resumeWritePayload(snapshot))
            : await ResumeService.create(resumeWritePayload(snapshot));
        applySavedResponse(response, sequence);
        await refreshList();
        return response;
    };

    const save = async () => run("save", async () => {
        await persist();
        showToast(t("resume.savedToast"), "success");
    });
    const publish = async () => run("publish", async () => {
        const saved = await persist();
        if (!versionName.trim()) throw new Error(t("resume.errorVersion"));
        await ResumeService.publish(saved.id, versionName.trim());
        setDraft(await ResumeService.get(saved.id));
        setVersionName(t("resume.nextNamedVersion", { title: saved.title }));
        await refreshList();
        showToast(t("resume.publishedToast"), "success");
    });
    const generateFromProfile = async () => run("generate", async () => {
        const response = await ResumeService.generate({
            title: draft.title.trim() || t("resume.defaultDraftTitle"),
            template_kind: draft.template_kind,
            career_goal_id: generationGoalId || null,
            photo_asset_id: draft.template_kind === "photo" ? draft.photo_asset_id : null,
        });
        setDraft(response);
        setDirty(false);
        setVersionComparison(null);
        await refreshList();
        showToast(t("resume.generatedToast"), "success");
    });
    const duplicate = async () => run("duplicate", async () => {
        if (!draft.id) return;
        const response = await ResumeService.duplicate(draft.id, { title: t("resume.duplicateTitle", { title: draft.title }) });
        setDraft(response);
        setDirty(false);
        setSyncPreview(null);
        await refreshList();
        showToast(t("resume.duplicatedToast"), "success");
    });
    const promoteClaim = async (blockId) => run("promote-claim", async () => {
        const saved = await persist();
        const response = await ResumeService.promoteClaim(saved.id, {
            expected_revision: saved.revision,
            expected_profile_revision: profile.revision,
            block_id: blockId,
        });
        const refreshedProfile = await CareerService.getProfile({ suppressGlobalError: true });
        setProfile(refreshedProfile);
        setDraft(response);
        setDirty(false);
        await refreshList();
        showToast(t("resume.promotedToast"), "success");
    });
    const reviewSync = async () => run("sync-preview", async () => {
        const response = await ResumeService.sync(draft.id, { expected_revision: draft.revision, mode: "preview", sections: [] });
        setSyncPreview(response);
        setSyncSelection([]);
    });
    const applySync = async (mode = "apply") => {
        if (mode === "reset" && !window.confirm(t("resume.resetConfirm"))) return;
        await run("sync", async () => {
            const response = await ResumeService.sync(draft.id, { expected_revision: draft.revision, mode, sections: mode === "apply" ? syncSelection : [] });
            setDraft(response.draft);
            setDirty(false);
            setSyncPreview(null);
            await refreshList();
            showToast(mode === "reset" ? t("resume.resetToast") : t("resume.syncToast"), "success");
        });
    };
    const uploadPhoto = async (file) => {
        if (!file) return;
        await run("photo", async () => {
            const asset = await CareerService.uploadPhoto(file);
            changeDraft({ photo_asset_id: asset.id });
            showToast(t("resume.photoToast"), "success");
        });
    };
    const remove = async () => {
        if (!draft.id || !window.confirm(t("resume.removeConfirm", { title: draft.title }))) return;
        await run("delete", async () => {
            await ResumeService.remove(draft.id);
            const next = await ResumeService.list();
            setResumes(next);
            setDraft(next.length ? await ResumeService.get(next[0].id) : freshDraft(profile.facts));
            setDirty(false);
        });
    };
    const compareVersions = async (versionIds) => run("compare-versions", async () => {
        if (versionIds.length !== 2) return;
        setVersionComparison(await ResumeService.compareVersions(versionIds[0], versionIds[1]));
    });
    const restoreVersion = async (version) => {
        if (!window.confirm(t("resume.restoreConfirm", { title: version.name }))) return;
        await run("restore-version", async () => {
            const response = await ResumeService.restoreVersion(draft.id, version.id, draft.revision);
            changeSequence.current += 1;
            setDraft(response);
            setDirty(false);
            setVersionComparison(null);
            await refreshList();
            showToast(t("resume.restoredToast"), "success");
        });
    };

    async function run(name, operation) {
        setBusy(name);
        setError("");
        try { await operation(); } catch (operationError) { setError(operationError.message); } finally { setBusy(""); }
    }

    useEffect(() => {
        if (!dirty || !draft || busy || autosaveInFlight.current) return undefined;
        if (!draft.title.trim() || !draft.selected_fact_ids.length) return undefined;
        if (draft.template_kind === "photo" && !draft.photo_asset_id) return undefined;
        const timer = window.setTimeout(async () => {
            autosaveInFlight.current = true;
            setBusy("autosave");
            setAutosaveState("saving");
            const sequence = changeSequence.current;
            const snapshot = draft;
            try {
                const response = snapshot.id
                    ? await ResumeService.update(snapshot.id, resumeWritePayload(snapshot))
                    : await ResumeService.create(resumeWritePayload(snapshot));
                applySavedResponse(response, sequence);
                setResumes(await ResumeService.list());
                setAutosaveState(changeSequence.current === sequence ? "saved" : "pending");
            } catch (autosaveError) {
                setAutosaveState("error");
                setError(t("resume.autosaveFailed", { message: autosaveError.message }));
            } finally {
                autosaveInFlight.current = false;
                setBusy("");
            }
        }, 1_000);
        return () => window.clearTimeout(timer);
    }, [busy, dirty, draft, t]);

    return { profile, resumes, draft, dirty, loading, busy, error, profileMissing, generationGoalId, syncPreview, syncSelection, versionName, versionComparison, autosaveState, initialize, loadDraft, changeDraft, startNew, save, publish, generateFromProfile, duplicate, promoteClaim, reviewSync, applySync, uploadPhoto, remove, compareVersions, restoreVersion, setGenerationGoalId, setSyncSelection, setVersionName, closeSync: () => setSyncPreview(null), setError };
}
