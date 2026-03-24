import { useState, useEffect, useRef, useCallback } from 'react';
import { JobService } from '../services/jobs';
import { SearchService } from '../services/search';
import { useSearchContext } from '../context/SearchContext';

export function useJobs(logout) {
  const { activeProfileIds } = useSearchContext();
  const [jobs, setJobs] = useState([]);
  const [searchProfiles, setSearchProfiles] = useState([]);
  const [isInitialLoad, setIsInitialLoad] = useState(true);

  // ... (lines 10-89 unchanged)
  
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
    setFilters({
      search_profile_id: "",
      min_score: "",
      max_distance: "",
      worth_applying: "",
      sort_by: "created_at",
      sort_order: "desc"
    });
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
