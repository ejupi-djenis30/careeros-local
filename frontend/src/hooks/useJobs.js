import { useState, useEffect, useCallback, useRef } from 'react';
import { JobService } from '../services/jobs';
import { SearchService } from '../services/search';
import { useSearchContext } from '../context/SearchContext';
import { useToast } from '../context/ToastContext';

const DEFAULT_FILTERS = {
  search_profile_id: '',
  min_score: '',
  max_distance: '',
  worth_applying: '',
  include_dismissed: '',
  sort_by: 'created_at',
  sort_order: 'desc'
};

const DEFAULT_PAGINATION = {
  page: 1,
  pages: 1,
  total: 0,
  total_applied: 0,
  avg_score: 0
};

const PAGE_SIZE = 20;

export function useJobs(logout) {
  const { activeProfileIds, statusHeartbeat } = useSearchContext();
  const { showToast } = useToast();
  const [jobs, setJobs] = useState([]);
  const [filtersState, setFiltersState] = useState(DEFAULT_FILTERS);
  const [pagination, setPaginationState] = useState(DEFAULT_PAGINATION);
  const [searchProfiles, setSearchProfiles] = useState([]);
  const isFirstFetch = useRef(true);
  const jobsRequestRef = useRef({ controller: null, id: 0 });
  const profilesRequestRef = useRef({ controller: null, id: 0 });
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [fetchError, setFetchError] = useState(null);
  const [pendingAppliedJobIds, setPendingAppliedJobIds] = useState([]);
  const filters = filtersState;

  const setPagination = useCallback((next) => {
    setIsRefreshing(true);
    setFetchError(null);
    jobsRequestRef.current.controller?.abort();
    setPaginationState((prev) => (typeof next === 'function' ? next(prev) : next));
  }, []);

  const setFilters = useCallback((next) => {
    setIsRefreshing(true);
    setFetchError(null);
    setFiltersState((prev) => {
      const resolved = typeof next === 'function' ? next(prev) : next;
      return { ...DEFAULT_FILTERS, ...resolved };
    });
    setPaginationState((prev) => (prev.page === 1 ? prev : { ...prev, page: 1 }));
    jobsRequestRef.current.controller?.abort();
  }, []);

  const requestJobs = useCallback(() => {
    const requestId = jobsRequestRef.current.id + 1;
    jobsRequestRef.current.controller?.abort();
    const controller = new AbortController();
    jobsRequestRef.current = { controller, id: requestId };

    return Promise.resolve()
      .then(() => JobService.getAll({
          ...filters,
          page: pagination.page,
          page_size: PAGE_SIZE
        }, controller.signal))
      .then((response) => {
        if (controller.signal.aborted || jobsRequestRef.current.id !== requestId) return;
        setJobs(response?.items || []);
        setPaginationState((prev) => ({
          ...prev,
          page: response?.page ?? prev.page,
          pages: response?.pages ?? 1,
          total: response?.total ?? 0,
          total_applied: response?.total_applied ?? 0,
          avg_score: response?.avg_score ?? 0
        }));
        setFetchError(null);
        isFirstFetch.current = false;
        setIsLoading(false);
        setIsRefreshing(false);
        jobsRequestRef.current.controller = null;
      })
      .catch((error) => {
        if (controller.signal.aborted || jobsRequestRef.current.id !== requestId || error.name === 'AbortError') return;
        if (error.message === 'UNAUTHORIZED' && logout) {
          logout();
        } else {
          console.error('Fetch jobs error:', error);
          setFetchError(error.message ? { message: error.message } : { messageKey: 'jobs.error.load' });
        }
        isFirstFetch.current = false;
        setIsLoading(false);
        setIsRefreshing(false);
        jobsRequestRef.current.controller = null;
      });
  }, [filters, pagination.page, logout]);

  const fetchJobs = useCallback((isBackground = false) => {
    if (!isBackground) {
      if (isFirstFetch.current) setIsLoading(true);
      else setIsRefreshing(true);
    }
    setFetchError(null);
    return requestJobs();
  }, [requestJobs]);

  const requestProfiles = useCallback(() => {
    const requestId = profilesRequestRef.current.id + 1;
    profilesRequestRef.current.controller?.abort();
    const controller = new AbortController();
    profilesRequestRef.current = { controller, id: requestId };

    return Promise.resolve()
      .then(() => SearchService.getProfiles({ signal: controller.signal }))
      .then((profiles) => {
        if (controller.signal.aborted || profilesRequestRef.current.id !== requestId) return;
        setSearchProfiles(Array.isArray(profiles) ? profiles : []);
        profilesRequestRef.current.controller = null;
      })
      .catch((error) => {
        if (controller.signal.aborted || profilesRequestRef.current.id !== requestId || error.name === 'AbortError') return;
        if (error.message === 'UNAUTHORIZED' && logout) {
          logout();
        } else {
          console.error('Failed to load search profiles', error);
          showToast(error.message ? { message: error.message } : { messageKey: 'jobs.error.profiles' });
        }
        profilesRequestRef.current.controller = null;
      });
  }, [logout, showToast]);

  useEffect(() => {
    void requestProfiles();
    return () => {
      profilesRequestRef.current.id += 1;
      profilesRequestRef.current.controller?.abort();
    };
  }, [requestProfiles]);

  useEffect(() => {
    void requestJobs();
    return () => {
      jobsRequestRef.current.id += 1;
      jobsRequestRef.current.controller?.abort();
    };
  }, [requestJobs]);

  // Active searches refresh job data via SearchContext's status polling heartbeat.
  useEffect(() => {
    if (activeProfileIds.length === 0 || statusHeartbeat === 0) {
      return;
    }

    void requestJobs();
  }, [activeProfileIds.length, statusHeartbeat, requestJobs]);

  // Idle fallback polling when no searches are active.
  useEffect(() => {
    if (activeProfileIds.length > 0) {
      return undefined;
    }

    const intervalTime = 30000;
    const interval = setInterval(() => {
      void requestJobs();
    }, intervalTime);

    return () => clearInterval(interval);
  }, [requestJobs, activeProfileIds.length]);

  // Visibility change handler for fresh data when tab is focused
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void requestJobs();
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, [requestJobs]);

  const toggleApplied = async (job) => {
    const jobId = String(job.id);
    if (pendingAppliedJobIds.includes(jobId)) {
      return;
    }

    setPendingAppliedJobIds(prev => (prev.includes(jobId) ? prev : [...prev, jobId]));
    try {
      const updated = await JobService.toggleApplied(job.id, !job.applied);
      setJobs(prev => prev.map(j => j.id === job.id ? { ...j, ...updated } : j));
    } catch (error) {
      if (error.message === "UNAUTHORIZED" && logout) { logout(); return; }
      console.error("Failed to update job", error);
      showToast(error.message ? { message: error.message } : { messageKey: 'jobs.error.update' });
    } finally {
      setPendingAppliedJobIds(prev => prev.filter(id => id !== jobId));
    }
  };

  const isAppliedPending = useCallback(
    (jobId) => pendingAppliedJobIds.includes(String(jobId)),
    [pendingAppliedJobIds]
  );

  const clearFilters = () => {
    setFilters(DEFAULT_FILTERS);
  };

  const dismissJob = async (job, feedbackSignal) => {
    const originalPosition = jobs.findIndex(j => j.id === job.id);
    try {
      const updated = await JobService.dismiss(job.id, feedbackSignal);
      // Remove from the list immediately (dismissed jobs are hidden by default)
      setJobs(prev => prev.filter(j => j.id !== job.id));
      // Refresh pagination count
      setPaginationState(prev => ({ ...prev, total: Math.max(0, prev.total - 1) }));
      // Undo toast — re-inserts job at original position
      showToast({ messageKey: 'jobs.dismissed' }, 'secondary', {
        labelKey: 'jobs.undo',
        onAction: async () => {
          try {
            const reactivated = await JobService.reactivate(job.id);
            const restoredJob = { ...job, ...reactivated, dismissed: false, dismissed_at: null, feedback_signal: null };
            setJobs(prev => {
              const newList = [...prev];
              newList.splice(Math.min(originalPosition, newList.length), 0, restoredJob);
              return newList;
            });
            setPaginationState(prev => ({ ...prev, total: prev.total + 1 }));
          } catch (undoError) {
            if (undoError.message === 'UNAUTHORIZED' && logout) { logout(); return; }
            console.error('Failed to undo dismiss', undoError);
            showToast(undoError.message ? { message: undoError.message } : { messageKey: 'jobs.error.undoDismiss' });
          }
        }
      }, 5000);
      return updated;
    } catch (error) {
      if (error.message === "UNAUTHORIZED" && logout) { logout(); return; }
      console.error("Failed to dismiss job", error);
      showToast(error.message ? { message: error.message } : { messageKey: 'jobs.error.dismiss' });
    }
  };

  const reactivateJob = async (job) => {
    try {
      const updated = await JobService.reactivate(job.id);
      setJobs(prev => prev.map(j => j.id === job.id ? { ...j, ...updated, dismissed: false, dismissed_at: null, feedback_signal: null } : j));
      return updated;
    } catch (error) {
      if (error.message === "UNAUTHORIZED" && logout) { logout(); return; }
      console.error("Failed to reactivate job", error);
      showToast(error.message ? { message: error.message } : { messageKey: 'jobs.error.reactivate' });
    }
  };

  return {
    jobs,
    pagination,
    setPagination,
    filters,
    setFilters,
    searchProfiles,
    fetchJobs,
    toggleApplied,
    isAppliedPending,
    dismissJob,
    reactivateJob,
    clearFilters,
    isLoading,
    isRefreshing,
    fetchError
  };
}
