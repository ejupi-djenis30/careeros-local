import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useJobs } from './useJobs';
import { JobService } from '../services/jobs';
import { SearchService } from '../services/search';

vi.mock('../services/jobs', () => ({
  JobService: {
    getAll: vi.fn(),
    toggleApplied: vi.fn(),
  }
}));

vi.mock('../services/search', () => ({
  SearchService: {
    getProfiles: vi.fn(),
  }
}));

describe('useJobs', () => {
  const mockJobs = [
    { id: 1, title: 'Job 1', applied: false },
    { id: 2, title: 'Job 2', applied: true },
  ];

  const mockPagination = {
    items: mockJobs,
    total: 2,
    pages: 1,
    page: 1,
    total_applied: 1,
    avg_score: 80
  };

  const mockProfiles = [{ id: 1, name: 'Profile 1' }];

  beforeEach(() => {
    vi.clearAllMocks();
    JobService.getAll.mockResolvedValue(mockPagination);
    SearchService.getProfiles.mockResolvedValue(mockProfiles);
  });

  it('fetches jobs and profiles on mount', async () => {
    const { result } = renderHook(() => useJobs());

    await waitFor(() => {
      expect(result.current.jobs).toEqual(mockJobs);
      expect(result.current.searchProfiles).toEqual(mockProfiles);
      expect(result.current.isInitialLoad).toBe(false);
    });
  });

  it('toggles applied status correctly', async () => {
    const { result } = renderHook(() => useJobs());
    
    await waitFor(() => expect(result.current.isInitialLoad).toBe(false));

    const updatedJob = { ...mockJobs[0], applied: true };
    JobService.toggleApplied.mockResolvedValue(updatedJob);

    await act(async () => {
      await result.current.toggleApplied(mockJobs[0]);
    });

    expect(result.current.jobs[0].applied).toBe(true);
    expect(JobService.toggleApplied).toHaveBeenCalledWith(1, true);
  });

  it('clears filters to default values', async () => {
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.isInitialLoad).toBe(false));

    await act(async () => {
      result.current.setFilters({ ...result.current.filters, min_score: 50 });
    });

    expect(result.current.filters.min_score).toBe(50);

    await act(async () => {
      result.current.clearFilters();
    });

    expect(result.current.filters.min_score).toBe("");
  });

  it('refetches jobs on visibility change', async () => {
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.jobs.length).toBe(2));
    
    JobService.getAll.mockClear();
    
    act(() => {
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(JobService.getAll).toHaveBeenCalled();
  });

  it('calls logout on UNAUTHORIZED error in fetchJobs', async () => {
    const logout = vi.fn();
    JobService.getAll.mockRejectedValue(new Error('UNAUTHORIZED'));
    
    renderHook(() => useJobs(logout));

    await waitFor(() => {
      expect(logout).toHaveBeenCalled();
    });
  });

  it('logs error on generic fetchJobs failure', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    JobService.getAll.mockRejectedValue(new Error('API ERROR'));
    
    renderHook(() => useJobs());

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalledWith('Fetch jobs error:', expect.any(Error));
    });
    consoleSpy.mockRestore();
  });

  it('calls logout on UNAUTHORIZED error in toggleApplied', async () => {
    const logout = vi.fn();
    const { result } = renderHook(() => useJobs(logout));
    await waitFor(() => expect(result.current.isInitialLoad).toBe(false));

    JobService.toggleApplied.mockRejectedValue(new Error('UNAUTHORIZED'));

    await act(async () => {
      await result.current.toggleApplied({ id: 1 });
    });

    expect(logout).toHaveBeenCalled();
  });

  it('logs error on generic toggleApplied failure', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.isInitialLoad).toBe(false));

    JobService.toggleApplied.mockRejectedValue(new Error('FAIL'));

    await act(async () => {
      await result.current.toggleApplied({ id: 1 });
    });

    expect(consoleSpy).toHaveBeenCalledWith('Failed to update job', expect.any(Error));
    consoleSpy.mockRestore();
  });

  it('logs error on getProfiles failure', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    SearchService.getProfiles.mockRejectedValue(new Error('PROFILE ERROR'));
    
    renderHook(() => useJobs());

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalledWith('Failed to load search profiles', expect.any(Error));
    });
    consoleSpy.mockRestore();
  });

  it('polls fetchJobs periodically', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
        renderHook(() => useJobs());
        await waitFor(() => expect(JobService.getAll).toHaveBeenCalledTimes(1));
        
        JobService.getAll.mockClear();
        
        await act(async () => {
            vi.advanceTimersByTime(11000);
        });
        
        await waitFor(() => expect(JobService.getAll).toHaveBeenCalledTimes(1));
    } finally {
        vi.useRealTimers();
    }
  });
});
