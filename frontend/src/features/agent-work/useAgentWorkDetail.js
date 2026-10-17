import { useCallback, useEffect, useRef, useState } from "react";
import { AgentWorkService } from "../../services/agentWork";
import { workErrorMessage } from "./agentWorkModel";

export function useAgentWorkDetail({ t, rememberWork, acknowledge }) {
    const [selectedWork, setSelectedWork] = useState(null);
    const [selectedProposal, setSelectedProposal] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [detailError, setDetailError] = useState("");
    const selection = useRef(null);
    const request = useRef({ controller: null, sequence: 0 });

    useEffect(() => {
        const activeRequest = request.current;
        return () => {
            activeRequest.controller?.abort();
            activeRequest.sequence += 1;
            selection.current = null;
        };
    }, []);

    const closeDetail = useCallback(() => {
        request.current.controller?.abort();
        request.current.controller = null;
        request.current.sequence += 1;
        selection.current = null;
        setSelectedWork(null);
        setSelectedProposal(null);
        setDetailLoading(false);
        setDetailError("");
    }, []);

    const loadDetail = useCallback(async (work) => {
        request.current.controller?.abort();
        const controller = new AbortController();
        request.current.controller = controller;
        const sequence = ++request.current.sequence;
        const isCurrent = () => !controller.signal.aborted && request.current.sequence === sequence
            && selection.current?.id === work.id;
        const next = rememberWork(work);
        selection.current = next;
        setSelectedWork(next);
        setSelectedProposal(null);
        setDetailLoading(true);
        setDetailError("");
        try {
            const response = await AgentWorkService.getWork(work.id, { signal: controller.signal });
            if (!isCurrent()) return;
            const detail = rememberWork(response);
            selection.current = detail;
            setSelectedWork(detail);
            setSelectedProposal(detail.proposal || null);
        } catch (reason) {
            if (isCurrent() && reason?.name !== "AbortError") {
                setDetailError(workErrorMessage(reason, t, "agentWork.error.loadDetail"));
            }
        } finally {
            if (isCurrent()) {
                request.current.controller = null;
                setDetailLoading(false);
            }
        }
    }, [rememberWork, t]);

    const updateWork = useCallback((work) => {
        const next = acknowledge(work);
        if (!next || selection.current?.id !== next.id) return;
        selection.current = next;
        setSelectedWork(next);
        setSelectedProposal(next.proposal || null);
    }, [acknowledge]);

    const refreshDetail = useCallback((id) => {
        if (id && selection.current?.id === id) return loadDetail(selection.current);
    }, [loadDetail]);

    return { selectedWork, selectedProposal, detailLoading, detailError, loadDetail, closeDetail, updateWork, refreshDetail };
}
