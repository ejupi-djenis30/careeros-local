import { useCallback, useEffect, useState } from "react";
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

    const loadDraft = useCallback(async (id) => {
        setBusy("load");
        setError("");
        try {
            setDraft(await ResumeService.get(id));
            setDirty(false);
            setSyncPreview(null);
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
    const changeDraft = (patch) => { setDraft((current) => ({ ...current, ...patch })); setDirty(true); };
    const startNew = () => { setDraft(newResumeDraft(profile.facts)); setDirty(false); setSyncPreview(null); };

    const persist = async () => {
        if (!draft.title.trim()) throw new Error("Inserisci un titolo per il CV");
        if (!draft.selected_fact_ids.length) throw new Error("Seleziona almeno un fatto di carriera");
        if (draft.template_kind === "photo" && !draft.photo_asset_id) throw new Error("Carica una foto per questo template");
        if (draft.id && !dirty) return draft;
        const response = draft.id
            ? await ResumeService.update(draft.id, resumeWritePayload(draft))
            : await ResumeService.create(resumeWritePayload(draft));
        setDraft(response);
        setDirty(false);
        await refreshList();
        return response;
    };

    const save = async () => run("save", async () => {
        await persist();
        showToast("Bozza CV salvata localmente.", "success");
    });
    const publish = async () => run("publish", async () => {
        const saved = await persist();
        await ResumeService.publish(saved.id);
        setDraft(await ResumeService.get(saved.id));
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

    async function run(name, operation) {
        setBusy(name);
        setError("");
        try { await operation(); } catch (operationError) { setError(operationError.message); } finally { setBusy(""); }
    }

    return { profile, resumes, draft, dirty, loading, busy, error, profileMissing, generationGoalId, syncPreview, syncSelection, initialize, loadDraft, changeDraft, startNew, save, publish, generateFromProfile, duplicate, promoteClaim, reviewSync, applySync, uploadPhoto, remove, setGenerationGoalId, setSyncSelection, closeSync: () => setSyncPreview(null), setError };
}
