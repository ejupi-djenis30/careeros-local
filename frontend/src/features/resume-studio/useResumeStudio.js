import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../lib/client";
import { CareerService } from "../../services/career";
import { ResumeService } from "../../services/resumes";
import { useToast } from "../../context/ToastContext";
import { newResumeDraft, resumeWritePayload } from "./resumeModel";

export function useResumeStudio() {
    const { showToast } = useToast();
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
    const [versionName, setVersionName] = useState("Versione CV");
    const [versionComparison, setVersionComparison] = useState(null);
    const [autosaveState, setAutosaveState] = useState("idle");
    const changeSequence = useRef(0);
    const autosaveInFlight = useRef(false);

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

    const initialize = useCallback(async () => {
        setLoading(true);
        try {
            const [loadedProfile, loadedResumes] = await Promise.all([
                CareerService.getProfile({ suppressGlobalError: true }),
                ResumeService.list(),
            ]);
            setProfile(loadedProfile);
            setResumes(loadedResumes);
            setGenerationGoalId(loadedProfile.goals?.find((goal) => goal.is_primary)?.id || loadedProfile.goals?.[0]?.id || "");
            setProfileMissing(false);
            setDraft(loadedResumes.length ? await ResumeService.get(loadedResumes[0].id) : newResumeDraft(loadedProfile.facts));
        } catch (loadError) {
            if (loadError instanceof ApiError && loadError.status === 404) setProfileMissing(true);
            else setError(loadError.message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { initialize(); }, [initialize]);
    const refreshList = async () => setResumes(await ResumeService.list());
    const changeDraft = (patch) => { changeSequence.current += 1; setDraft((current) => ({ ...current, ...patch })); setDirty(true); setAutosaveState("pending"); };
    const startNew = () => { changeSequence.current += 1; setDraft(newResumeDraft(profile.facts)); setDirty(false); setSyncPreview(null); setVersionComparison(null); setVersionName("Versione CV"); setAutosaveState("idle"); };

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
        if (!draft.title.trim()) throw new Error("Inserisci un titolo per il CV");
        if (!draft.selected_fact_ids.length) throw new Error("Seleziona almeno un fatto di carriera");
        if (draft.template_kind === "photo" && !draft.photo_asset_id) throw new Error("Carica una foto per questo template");
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
        showToast("Bozza CV salvata localmente.", "success");
    });
    const publish = async () => run("publish", async () => {
        const saved = await persist();
        if (!versionName.trim()) throw new Error("Inserisci un nome per la versione");
        await ResumeService.publish(saved.id, versionName.trim());
        setDraft(await ResumeService.get(saved.id));
        setVersionName(`${saved.title} · nuova versione`);
        await refreshList();
        showToast("PDF e DOCX generati e verificati.", "success");
    });
    const generateFromProfile = async () => run("generate", async () => {
        const response = await ResumeService.generate({
            title: draft.title.trim() || "CV dal profilo",
            template_kind: draft.template_kind,
            career_goal_id: generationGoalId || null,
            photo_asset_id: draft.template_kind === "photo" ? draft.photo_asset_id : null,
        });
        setDraft(response);
        setDirty(false);
        setVersionComparison(null);
        await refreshList();
        showToast("CV creato automaticamente dal Career Vault.", "success");
    });
    const duplicate = async () => run("duplicate", async () => {
        if (!draft.id) return;
        const response = await ResumeService.duplicate(draft.id, { title: `${draft.title} · copia` });
        setDraft(response);
        setDirty(false);
        setSyncPreview(null);
        await refreshList();
        showToast("Copia indipendente creata localmente.", "success");
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
        showToast("Claim salvato come fatto verificato nel Career Vault.", "success");
    });
    const reviewSync = async () => run("sync-preview", async () => {
        const response = await ResumeService.sync(draft.id, { expected_revision: draft.revision, mode: "preview", sections: [] });
        setSyncPreview(response);
        setSyncSelection([]);
    });
    const applySync = async (mode = "apply") => {
        if (mode === "reset" && !window.confirm("Rigenerare tutto dal profilo? Le modifiche manuali del canvas saranno rimosse.")) return;
        await run("sync", async () => {
            const response = await ResumeService.sync(draft.id, { expected_revision: draft.revision, mode, sections: mode === "apply" ? syncSelection : [] });
            setDraft(response.draft);
            setDirty(false);
            setSyncPreview(null);
            await refreshList();
            showToast(mode === "reset" ? "CV rigenerato dal profilo." : "Sezioni sincronizzate; override preservati.", "success");
        });
    };
    const uploadPhoto = async (file) => {
        if (!file) return;
        await run("photo", async () => {
            const asset = await CareerService.uploadPhoto(file);
            changeDraft({ photo_asset_id: asset.id });
            showToast("Foto normalizzata: metadati EXIF rimossi.", "success");
        });
    };
    const remove = async () => {
        if (!draft.id || !window.confirm(`Eliminare la bozza “${draft.title}”? Le versioni pubblicate collegate saranno rimosse.`)) return;
        await run("delete", async () => {
            await ResumeService.remove(draft.id);
            const next = await ResumeService.list();
            setResumes(next);
            setDraft(next.length ? await ResumeService.get(next[0].id) : newResumeDraft(profile.facts));
            setDirty(false);
        });
    };
    const compareVersions = async (versionIds) => run("compare-versions", async () => {
        if (versionIds.length !== 2) return;
        setVersionComparison(await ResumeService.compareVersions(versionIds[0], versionIds[1]));
    });
    const restoreVersion = async (version) => {
        if (!window.confirm(`Ripristinare “${version.name}” nella bozza? Le versioni pubblicate resteranno intatte.`)) return;
        await run("restore-version", async () => {
            const response = await ResumeService.restoreVersion(draft.id, version.id, draft.revision);
            changeSequence.current += 1;
            setDraft(response);
            setDirty(false);
            setVersionComparison(null);
            await refreshList();
            showToast("Versione ripristinata in una nuova revisione della bozza.", "success");
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
                setError(`Autosave non riuscito: ${autosaveError.message}`);
            } finally {
                autosaveInFlight.current = false;
                setBusy("");
            }
        }, 1_000);
        return () => window.clearTimeout(timer);
    }, [busy, dirty, draft]);

    return { profile, resumes, draft, dirty, loading, busy, error, profileMissing, generationGoalId, syncPreview, syncSelection, versionName, versionComparison, autosaveState, initialize, loadDraft, changeDraft, startNew, save, publish, generateFromProfile, duplicate, promoteClaim, reviewSync, applySync, uploadPhoto, remove, compareVersions, restoreVersion, setGenerationGoalId, setSyncSelection, setVersionName, closeSync: () => setSyncPreview(null), setError };
}
