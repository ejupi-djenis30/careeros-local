import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { ApplicationService } from "../../services/applications";
import { useToast } from "../../context/ToastContext";
import { STAGES } from "./applicationModel";
import { useApplicationCatalog } from "./useApplicationCatalog";

const emptyForm = (jobId = "") => ({
    job_id: jobId, title: "", company: "", location: "", external_url: "", description: "",
    initial_stage: "saved", resume_version_id: "", note: "",
});

export function useApplicationsWorkspace() {
    const catalog = useApplicationCatalog();
    const { applications, loading, setError, requestApplications, requestCampaigns, reconcileApplication } = catalog;
    const [searchParams, setSearchParams] = useSearchParams();
    const requestedApplicationId = (searchParams.get("applicationId") || "").trim();
    const requestedJobId = (searchParams.get("jobId") || "").trim();
    const { showToast } = useToast();
    const [selected, setSelected] = useState(null);
    const [creating, setCreating] = useState(false);
    const [showCreate, updateShowCreate] = useState(Boolean(requestedJobId) && !requestedApplicationId);
    const [openingId, setOpeningId] = useState("");
    const [agendaRevision, setAgendaRevision] = useState(0);
    const [form, setForm] = useState(emptyForm(requestedJobId));
    const [filters, setFilters] = useState({ campaignId: "", query: "", stage: "", priority: "" });
    const [detailOpener, setDetailOpener] = useState(null);
    const detailRequest = useRef({ controller: null, id: 0 });
    const backgroundRef = useRef(null);
    const addApplicationRef = useRef(null);
    const applicationCardRefs = useRef(new Map());
    const deepLinkAttempt = useRef("");
    const mounted = useRef(false);
    const createSession = useRef(0);
    const setShowCreate = (next) => {
        createSession.current += 1;
        updateShowCreate(next);
    };

    useEffect(() => {
        mounted.current = true;
        return () => {
            mounted.current = false;
            detailRequest.current.id += 1;
            detailRequest.current.controller?.abort();
        };
    }, []);

    const handleCampaignImported = useCallback(async (result) => {
        await Promise.all([requestApplications(), requestCampaigns()]);
        if (!mounted.current) return;
        setAgendaRevision((value) => value + 1);
        showToast({ messageKey: "applications.campaignImported", values: { count: result.application_count } }, "success");
    }, [requestApplications, requestCampaigns, setAgendaRevision, showToast]);

    const filteredApplications = useMemo(() => applications.filter((app) => {
        if (filters.campaignId && app.campaign_id !== filters.campaignId) return false;
        if (filters.stage && app.current_stage !== filters.stage) return false;
        if (filters.priority && app.campaign_priority !== filters.priority) return false;
        const query = filters.query.toLowerCase().trim();
        return !query || [app.title, app.company, app.location, app.source_application_id, app.campaign_platform, app.campaign_category]
            .some((value) => (value || "").toLowerCase().includes(query));
    }), [applications, filters]);
    const grouped = useMemo(() => Object.fromEntries(STAGES.map((stage) => [stage, filteredApplications.filter((item) => item.current_stage === stage)])), [filteredApplications]);
    const closed = grouped.rejected.length + grouped.withdrawn.length + grouped.archived.length;

    const openApplication = useCallback(async (id, opener) => {
        const requestId = detailRequest.current.id + 1;
        detailRequest.current.controller?.abort();
        const controller = new AbortController();
        detailRequest.current = { controller, id: requestId };
        setError("");
        setOpeningId(id);
        try {
            const detail = await ApplicationService.get(id, { signal: controller.signal });
            if (controller.signal.aborted || detailRequest.current.id !== requestId) return;
            setDetailOpener(opener);
            setSelected(detail);
        } catch (loadError) {
            if (!controller.signal.aborted && detailRequest.current.id === requestId) setError(loadError.message);
        } finally {
            if (detailRequest.current.id === requestId) {
                detailRequest.current.controller = null;
                setOpeningId("");
            }
        }
    }, [setDetailOpener, setError, setOpeningId, setSelected]);

    useEffect(() => {
        if (!requestedApplicationId) {
            deepLinkAttempt.current = "";
            return;
        }
        if (loading || deepLinkAttempt.current === requestedApplicationId) return;
        deepLinkAttempt.current = requestedApplicationId;
        const opener = applicationCardRefs.current.get(requestedApplicationId) ?? addApplicationRef.current;
        void openApplication(requestedApplicationId, opener);
    }, [loading, openApplication, requestedApplicationId]);

    const closeApplication = () => {
        detailRequest.current.id += 1;
        detailRequest.current.controller?.abort();
        detailRequest.current.controller = null;
        setOpeningId("");
        setSelected(null);
        if (!searchParams.has("applicationId")) return;
        const nextParams = new URLSearchParams(searchParams);
        nextParams.delete("applicationId");
        setSearchParams(nextParams, { replace: true });
    };

    const create = async (event) => {
        event.preventDefault();
        const selectionRequestId = detailRequest.current.id;
        const formSession = createSession.current;
        setCreating(true);
        setError("");
        try {
            const jobSource = form.job_id ? { job_id: Number(form.job_id) } : { manual_job: {
                title: form.title.trim(), company: form.company.trim(),
                location: form.location.trim() || null, external_url: form.external_url.trim() || null,
                description: form.description.trim() || null,
            } };
            const application = await ApplicationService.create({
                ...jobSource, initial_stage: form.initial_stage,
                resume_version_id: form.resume_version_id || null, note: form.note.trim() || null,
            });
            await requestApplications();
            if (!mounted.current) return;
            setAgendaRevision((value) => value + 1);
            if (createSession.current === formSession) {
                if (detailRequest.current.id === selectionRequestId) {
                    setDetailOpener(addApplicationRef.current);
                    setSelected(application);
                    setSearchParams({});
                }
                setShowCreate(false);
                setForm(emptyForm());
            }
            showToast({ messageKey: "applications.added" }, "success");
        } catch (createError) {
            if (mounted.current && createSession.current === formSession) setError(createError.message);
        } finally {
            if (mounted.current) setCreating(false);
        }
    };

    const handleChanged = (updated) => {
        if (!mounted.current) return;
        setSelected((current) => current?.id === updated.id && current.revision <= updated.revision ? updated : current);
        setAgendaRevision((value) => value + 1);
        reconcileApplication(updated);
    };

    return {
        ...catalog, selected, creating, showCreate, setShowCreate, openingId, agendaRevision,
        form, setForm, filters, setFilters, detailOpener, backgroundRef, addApplicationRef,
        applicationCardRefs, requestedApplicationId, filteredApplications, grouped, closed,
        handleCampaignImported, openApplication, closeApplication, create, handleChanged,
    };
}
