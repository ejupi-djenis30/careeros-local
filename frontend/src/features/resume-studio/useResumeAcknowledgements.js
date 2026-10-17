import { useLayoutEffect, useRef, useState } from "react";
import { CareerService } from "../../services/career";
import { ResumeService } from "../../services/resumes";

// These reads reconcile committed mutations. Retrying them must never repeat a write.
export function useResumeAcknowledgements({ run, profile, draft, changeSequence, persist,
    applySavedResponse, installDraft, freshDraft, setDraft, setDirty, setAutosaveState,
    setResumes, setProfile, setError, setVersionComparison, showToast, t }) {
    const [pending, setPending] = useState(null);
    const pendingRef = useRef(null);
    const selectedDraft = useRef(draft);
    useLayoutEffect(() => { selectedDraft.current = draft; }, [draft]);
    const remember = (value) => {
        pendingRef.current = value;
        setPending(value);
    };

    const refresh = async (request, work) => {
        // Preserve missing shared profile/catalog data even if another editor is opened.
        // Any successor selection still belongs to the original deletion session.
        remember(work);
        const remaining = { ...work, profile: false, catalog: false };
        if (work.profile) {
            try {
                const response = await CareerService.getProfile(request.options);
                if (!request.isCurrent()) return;
                setProfile(response);
            } catch {
                if (!request.isCurrent()) return;
                remaining.profile = true;
            }
        }
        if (work.catalog) {
            try {
                const resumes = await ResumeService.list(request.options);
                if (!request.isCurrent()) return;
                setResumes(resumes);
                if (resumes.length && work.canSelectSuccessor?.()) {
                    const successor = await ResumeService.get(resumes[0].id, request.options);
                    if (!request.isCurrent()) return;
                    if (work.canSelectSuccessor()) installDraft(successor);
                }
            } catch {
                if (!request.isCurrent()) return;
                remaining.catalog = true;
            }
        }
        if (request.isCurrent()) remember(remaining.profile || remaining.catalog ? remaining : null);
    };

    const retryRefresh = () => {
        const work = pendingRef.current;
        if (!work) return;
        return run("refresh", (request) => refresh(request, work));
    };

    const promoteClaim = async (blockId) => {
        if (pending?.profile) {
            setError({ messageKey: "resume.reload" });
            return;
        }
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
            applySavedResponse(response, sequence, request);
            setVersionComparison(null);
            showToast({ messageKey: "resume.promotedToast" }, "success");
            await refresh(request, { profile: true, catalog: true });
        });
    };

    const remove = async () => {
        if (!draft.id || !window.confirm(t("resume.removeConfirm", { title: draft.title }))) return;
        const sequence = changeSequence.current;
        return run("delete", async (request) => {
            await ResumeService.remove(draft.id, request.options);
            if (!request.isCurrent()) return;
            setResumes((current) => current.filter((resume) => resume.id !== draft.id));
            if (sequence === changeSequence.current) installDraft(freshDraft(profile.facts));
            else {
                setDraft((current) => request.isCurrent()
                    ? { ...current, id: null, revision: null, versions: [] } : current);
                setDirty(true);
                setAutosaveState("pending");
            }
            const outstanding = pendingRef.current;
            await refresh(request, {
                profile: Boolean(outstanding?.profile),
                catalog: true,
                canSelectSuccessor: () => request.isSessionCurrent()
                    && changeSequence.current === sequence
                    && [null, draft.id].includes(selectedDraft.current?.id),
            });
        });
    };

    return { remove, promoteClaim, retryRefresh, refreshPending: Boolean(pending),
        profileRefreshPending: Boolean(pending?.profile) };
}
