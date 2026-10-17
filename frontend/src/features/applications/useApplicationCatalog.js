import { useCallback, useEffect, useRef, useState } from "react";
import { ApplicationService } from "../../services/applications";
import { CampaignService } from "../../services/campaigns";
import { ResumeService } from "../../services/resumes";

export function useApplicationCatalog() {
    const [applications, setApplications] = useState([]);
    const [campaigns, setCampaigns] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [resumeDrafts, setResumeDrafts] = useState([]);
    const [resumeVersions, setResumeVersions] = useState([]);
    const [resumeMetadataStatus, setResumeMetadataStatus] = useState("loading");
    const [resumeMetadataRevision, setResumeMetadataRevision] = useState(0);
    const applicationRequest = useRef({ controller: null, id: 0 });
    const campaignRequest = useRef({ controller: null, id: 0 });

    const requestCampaigns = useCallback(() => {
        const requestId = campaignRequest.current.id + 1;
        campaignRequest.current.controller?.abort();
        const controller = new AbortController();
        campaignRequest.current = { controller, id: requestId };
        return CampaignService.list({ signal: controller.signal })
            .then((items) => {
                if (controller.signal.aborted || campaignRequest.current.id !== requestId) return;
                setCampaigns(Array.isArray(items) ? items : []);
            })
            .catch((loadError) => {
                if (controller.signal.aborted || loadError?.name === "AbortError" || campaignRequest.current.id !== requestId) return;
            })
            .finally(() => {
                if (!controller.signal.aborted && campaignRequest.current.id === requestId) campaignRequest.current.controller = null;
            });
    }, []);

    const requestApplications = useCallback(() => {
        const requestId = applicationRequest.current.id + 1;
        applicationRequest.current.controller?.abort();
        const controller = new AbortController();
        applicationRequest.current = { controller, id: requestId };
        return ApplicationService.list({ signal: controller.signal })
            .then((items) => {
                if (controller.signal.aborted || applicationRequest.current.id !== requestId) return;
                setApplications(Array.isArray(items) ? items : []);
                setError("");
            })
            .catch((loadError) => {
                if (controller.signal.aborted || loadError?.name === "AbortError" || applicationRequest.current.id !== requestId) return;
                setError(loadError.message);
            })
            .finally(() => {
                if (!controller.signal.aborted && applicationRequest.current.id === requestId) {
                    applicationRequest.current.controller = null;
                    setLoading(false);
                }
            });
    }, []);

    useEffect(() => {
        void requestApplications();
        void requestCampaigns();
        return () => {
            for (const request of [applicationRequest, campaignRequest]) {
                request.current.id += 1;
                request.current.controller?.abort();
                request.current.controller = null;
            }
        };
    }, [requestApplications, requestCampaigns]);

    useEffect(() => {
        const controller = new AbortController();
        ResumeService.list({ signal: controller.signal })
            .then((items) => Promise.all(items.map((item) => ResumeService.get(item.id, { signal: controller.signal }))))
            .then((drafts) => {
                if (controller.signal.aborted) return;
                setResumeDrafts(drafts);
                setResumeVersions(drafts.flatMap((draft) => draft.versions.map((version) => ({ ...version, draft_id: draft.id, id: version.id, label: `${draft.title} \u00b7 v${version.semantic_version}`, selected_fact_ids: version.selected_fact_ids || [] }))));
                setResumeMetadataStatus("ready");
            })
            .catch((loadError) => {
                if (controller.signal.aborted || loadError?.name === "AbortError") return;
                setResumeMetadataStatus("error");
            });
        return () => controller.abort();
    }, [resumeMetadataRevision]);

    const retryResumeMetadata = () => {
        setResumeMetadataStatus("loading");
        setResumeMetadataRevision((current) => current + 1);
    };

    const reconcileApplication = useCallback((updated) => {
        setApplications((items) => items.map((item) => {
            if (item.id !== updated.id || item.revision > updated.revision) return item;
            return {
                ...item,
                revision: updated.revision,
                current_stage: updated.current_stage,
                updated_at: updated.updated_at,
                title: updated.job_snapshot?.title ?? item.title,
                company: updated.job_snapshot?.company ?? item.company,
                location: updated.job_snapshot?.location ?? item.location,
            };
        }));
        void requestApplications();
    }, [requestApplications]);

    return {
        applications, campaigns, loading, error, setError,
        resumeDrafts, resumeVersions, resumeMetadataStatus, retryResumeMetadata,
        requestApplications, requestCampaigns, reconcileApplication,
    };
}
