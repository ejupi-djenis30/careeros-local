import { useLayoutEffect, useRef } from 'react';
import { JobService } from '../services/jobs';
import { reportUiFailure } from '../lib/uiDiagnostics';

export function useJobMutations({ jobs, filters, page, requestJobs, setJobs, setPagination, logout, showToast }) {
  const mounted = useRef(false);
  const latest = useRef(null);
  const queryKey = JSON.stringify([filters, page]);

  useLayoutEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  useLayoutEffect(() => {
    latest.current = { jobs, filters, queryKey, requestJobs };
  }, [jobs, filters, queryKey, requestJobs]);

  const reportError = (error, operation, messageKey) => {
    if (!mounted.current) return;
    if (error.message === 'UNAUTHORIZED' && logout) { logout(); return; }
    reportUiFailure(operation);
    showToast(error.message ? { message: error.message } : { messageKey });
  };

  const reactivate = async (job, undo) => {
    if (!mounted.current) return;
    try {
      const updated = await JobService.reactivate(job.id);
      if (!mounted.current) return updated;
      // The current query decides membership and ordering, including Undo after navigation.
      void latest.current.requestJobs();
      return updated;
    } catch (error) {
      reportError(error, undo ? 'jobs_undo' : 'jobs_reactivate', undo ? 'jobs.error.undoDismiss' : 'jobs.error.reactivate');
    }
  };

  const dismissJob = async (job, feedbackSignal) => {
    const originQuery = latest.current.queryKey;
    try {
      const updated = await JobService.dismiss(job.id, feedbackSignal);
      if (!mounted.current) return updated;
      const current = latest.current;
      if (current.queryKey === originQuery && current.jobs.some((item) => item.id === job.id)) {
        if (current.filters.include_dismissed === true || current.filters.include_dismissed === 'true') {
          setJobs((items) => items.map((item) => item.id === job.id ? { ...item, ...updated } : item));
        } else {
          setJobs((items) => items.filter((item) => item.id !== job.id));
          setPagination((previous) => ({ ...previous, total: Math.max(0, previous.total - 1) }));
        }
      }
      void current.requestJobs();
      showToast({ messageKey: 'jobs.dismissed' }, 'secondary', {
        labelKey: 'jobs.undo',
        onAction: () => reactivate(job, true),
      }, 5000);
      return updated;
    } catch (error) {
      reportError(error, 'jobs_dismiss', 'jobs.error.dismiss');
    }
  };

  return { dismissJob, reactivateJob: (job) => reactivate(job, false) };
}
