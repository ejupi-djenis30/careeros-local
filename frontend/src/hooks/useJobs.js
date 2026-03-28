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
  const { activeProfileIds } = useSearchContext();
  const { showToast } = useToast();
  const [jobs, setJobs] = useState([]);
  const [filtersState, setFiltersState] = useState(DEFAULT_FILTERS);
  const [pagination, setPaginationState] = useState(DEFAULT_PAGINATION);
  const [searchProfiles, setSearchProfiles] = useState([]);
  const isFirstFetch = useRef(true);
  const fetchAbortControllerRef = useRef(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [fetchError, setFetchError] = useState(null);
  const [pendingAppliedJobIds, setPendingAppliedJobIds] = useState([]);
  const filters = filtersState;

  const setPagination = useCallback((next) => {
    setPaginationState((prev) => (typeof next === 'function' ? next(prev) : next));
  }, []);

  const setFilters = useCallback((next) => {
    setFiltersState((prev) => {
      const resolved = typeof next === 'function' ? next(prev) : next;
      return { ...DEFAULT_FILTERS, ...resolved };
    });
    setPaginationState((prev) => (prev.page === 1 ? prev : { ...prev, page: 1 }));
    // Abort any in-flight fetch so a stale response can't overwrite the new filter state
    if (fetchAbortControllerRef.current) {
      fetchAbortControllerRef.current.abort();
    }
  }, []);

  const fetchJobs = useCallback(async (isBackground = false) => {
    if (!isBackground) {
      if (isFirstFetch.current) {
        setIsLoading(true);
      } else {
        setIsRefreshing(true);
      }
    }

    // Cancel any previous in-flight request before starting a new one
    if (fetchAbortControllerRef.current) {
      fetchAbortControllerRef.current.abort();
    }
    const controller = new AbortController();
    fetchAbortControllerRef.current = controller;

    try {
      const response = await JobService.getAll({
        ...filters,
        page: pagination.page,
        page_size: PAGE_SIZE
      }, controller.signal);

      // Ignore stale responses that completed after a newer request was aborted
      if (controller.signal.aborted) return;

      setJobs(response?.items || []);
      setPaginationState((prev) => ({
        ...prev,
        page: response?.page ?? prev.page,
        pages: response?.pages ?? 1,
        total: response?.total ?? 0,
        total_applied: response?.total_applied ?? 0,
        avg_score: response?.avg_score ?? 0
      }));
    } catch (error) {
      if (error.name === 'AbortError') return; // Stale request — discard silently
      if (error.message === 'UNAUTHORIZED' && logout) {
        logout();
        return;
      }
      console.error('Fetch jobs error:', error);
      setFetchError(error.message || 'Failed to load jobs.');
    } finally {
      if (!controller.signal.aborted) {
        isFirstFetch.current = false;
        setIsLoading(false);
        setIsRefreshing(false);
      }
    }
  }, [filters, pagination.page, logout]);

  const fetchProfiles = useCallback(async () => {
    try {
      const profiles = await SearchService.getProfiles();
      setSearchProfiles(Array.isArray(profiles) ? profiles : []);
    } catch (error) {
      if (error.message === 'UNAUTHORIZED' && logout) {
        logout();
        return;
      }
      console.error('Failed to load search profiles', error);
    }
  }, [logout]);

  useEffect(() => {
    fetchProfiles();
  }, [fetchProfiles]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);
  
  // OPT-3: Background polling intervals - adjusted based on activity
  useEffect(() => {
    const isSearching = activeProfileIds.length > 0;
    const intervalTime = isSearching ? 5000 : 30000; // 5s if searching, 30s if idle
    
    const interval = setInterval(() => {
      fetchJobs(true);
    }, intervalTime);
    
    return () => clearInterval(interval);
  }, [fetchJobs, activeProfileIds.length]);

  // Visibility change handler for fresh data when tab is focused
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        fetchJobs(true);
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, [fetchJobs]);

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
      setPagination(prev => ({ ...prev, total: Math.max(0, prev.total - 1) }));
      // Undo toast — re-inserts job at original position
      showToast('Job dismissed', 'secondary', {
        label: 'Undo',
        onAction: async () => {
          try {
            const reactivated = await JobService.reactivate(job.id);
            const restoredJob = { ...job, ...reactivated, dismissed: false, dismissed_at: null, feedback_signal: null };
            setJobs(prev => {
              const newList = [...prev];
              newList.splice(Math.min(originalPosition, newList.length), 0, restoredJob);
              return newList;
            });
            setPagination(prev => ({ ...prev, total: prev.total + 1 }));
          } catch (undoError) {
            if (undoError.message === 'UNAUTHORIZED' && logout) { logout(); return; }
            console.error('Failed to undo dismiss', undoError);
          }
        }
      }, 5000);
      return updated;
    } catch (error) {
      if (error.message === "UNAUTHORIZED" && logout) { logout(); return; }
      console.error("Failed to dismiss job", error);
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
