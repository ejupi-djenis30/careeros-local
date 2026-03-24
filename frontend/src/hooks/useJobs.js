import { useState, useEffect, useCallback } from 'react';
import { JobService } from '../services/jobs';
import { SearchService } from '../services/search';
import { useSearchContext } from '../context/SearchContext';

const DEFAULT_FILTERS = {
  search_profile_id: '',
  min_score: '',
  max_distance: '',
  worth_applying: '',
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
  const [jobs, setJobs] = useState([]);
  const [filtersState, setFiltersState] = useState(DEFAULT_FILTERS);
  const [pagination, setPaginationState] = useState(DEFAULT_PAGINATION);
  const [searchProfiles, setSearchProfiles] = useState([]);
  const [isInitialLoad, setIsInitialLoad] = useState(true);
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
  }, []);

  const fetchJobs = useCallback(async () => {
    try {
      const response = await JobService.getAll({
        ...filters,
        page: pagination.page,
        page_size: PAGE_SIZE
      });

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
      if (error.message === 'UNAUTHORIZED' && logout) {
        logout();
        return;
      }
      console.error('Fetch jobs error:', error);
    } finally {
      setIsInitialLoad(false);
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
    try {
      // HALF-8: Backend patch returns updated Job, ensure we use it
      const updated = await JobService.toggleApplied(job.id, !job.applied);
      // Pydantic/SQLAlchemy might return a different object but same ID
      setJobs(prev => prev.map(j => j.id === job.id ? { ...j, ...updated } : j));
    } catch (error) {
      if (error.message === "UNAUTHORIZED" && logout) { logout(); return; }
      console.error("Failed to update job", error);
    }
  };

  const clearFilters = () => {
    setFilters(DEFAULT_FILTERS);
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
    clearFilters,
    isInitialLoad
  };
}
