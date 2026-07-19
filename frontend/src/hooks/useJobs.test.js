import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useJobs } from './useJobs';
import { JobService } from '../services/jobs';
import { SearchService } from '../services/search';

let mockActiveProfileIds = [];
let mockStatusHeartbeat = 0;

vi.mock('../services/jobs', () => ({
  JobService: {
    getAll: vi.fn(),
    toggleApplied: vi.fn(),
  }
}));

vi.mock('../context/SearchContext', () => ({
  useSearchContext: () => ({
    activeProfileIds: mockActiveProfileIds,
    statusHeartbeat: mockStatusHeartbeat,
  })
}));

vi.mock('../services/search', () => ({
  SearchService: {
    getProfiles: vi.fn(),
  }
}));

vi.mock('../context/ToastContext', () => ({
  useToast: () => ({ showToast: vi.fn(), clearToast: vi.fn() })
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
    mockActiveProfileIds = [];
    mockStatusHeartbeat = 0;
    JobService.getAll.mockResolvedValue(mockPagination);
    SearchService.getProfiles.mockResolvedValue(mockProfiles);
  });

  it('fetches jobs and profiles on mount', async () => {
    const { result } = renderHook(() => useJobs());

    await waitFor(() => {
      expect(result.current.jobs).toEqual(mockJobs);
      expect(result.current.searchProfiles).toEqual(mockProfiles);
      expect(result.current.isLoading).toBe(false);
    });
  });

  it('toggles applied status correctly', async () => {
    const { result } = renderHook(() => useJobs());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const updatedJob = { ...mockJobs[0], applied: true };
    JobService.toggleApplied.mockResolvedValue(updatedJob);

    await act(async () => {
      await result.current.toggleApplied(mockJobs[0]);
    });

    expect(result.current.jobs[0].applied).toBe(true);
    expect(JobService.toggleApplied).toHaveBeenCalledWith(1, true);
  });

  it('prevents overlapping applied toggles for the same job', async () => {
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let resolveToggle;
    JobService.toggleApplied.mockReturnValue(
      new Promise((resolve) => {
        resolveToggle = resolve;
      })
    );

    let firstCall;
    await act(async () => {
      firstCall = result.current.toggleApplied(mockJobs[0]);
      await Promise.resolve();
    });

    expect(result.current.isAppliedPending(1)).toBe(true);

    await act(async () => {
      await result.current.toggleApplied(mockJobs[0]);
    });

    expect(JobService.toggleApplied).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveToggle({ ...mockJobs[0], applied: true });
      await firstCall;
    });

    expect(result.current.isAppliedPending(1)).toBe(false);
    expect(result.current.jobs[0].applied).toBe(true);
  });

  it('clears filters to default values', async () => {
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

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

    await act(async () => {
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
      await Promise.resolve();
    });

    await waitFor(() => expect(JobService.getAll).toHaveBeenCalled());
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
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    JobService.toggleApplied.mockRejectedValue(new Error('UNAUTHORIZED'));

    await act(async () => {
      await result.current.toggleApplied({ id: 1 });
    });

    expect(logout).toHaveBeenCalled();
  });

  it('logs error on generic toggleApplied failure', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    JobService.toggleApplied.mockRejectedValue(new Error('FAIL'));

    await act(async () => {
      await result.current.toggleApplied({ id: 1 });
    });

    expect(consoleSpy).toHaveBeenCalledWith('Failed to update job', expect.any(Error));
    consoleSpy.mockRestore();
  });

  it('clears pending applied state after a failed update', async () => {
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    JobService.toggleApplied.mockRejectedValue(new Error('FAIL'));

    await act(async () => {
      await result.current.toggleApplied(mockJobs[0]);
    });

    expect(result.current.isAppliedPending(1)).toBe(false);
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

  it('refreshes jobs when search status heartbeat advances during an active search', async () => {
    mockActiveProfileIds = ['1'];
    const { rerender } = renderHook(() => useJobs());
    await waitFor(() => expect(JobService.getAll).toHaveBeenCalledTimes(1));

    JobService.getAll.mockClear();
    mockStatusHeartbeat = 1;
    rerender();

    await waitFor(() => expect(JobService.getAll).toHaveBeenCalledTimes(1));
  });

  it('uses the idle polling interval when no searches are active', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      renderHook(() => useJobs());
      await waitFor(() => expect(JobService.getAll).toHaveBeenCalledTimes(1));

      JobService.getAll.mockClear();

      await act(async () => {
        vi.advanceTimersByTime(29000);
      });

      expect(JobService.getAll).not.toHaveBeenCalled();

      await act(async () => {
        vi.advanceTimersByTime(1500);
      });

      await waitFor(() => expect(JobService.getAll).toHaveBeenCalledTimes(1));
    } finally {
      vi.useRealTimers();
    }
  });

  it('aborts stale in-flight request when filters change', async () => {
    let resolveStale;
    JobService.getAll
      .mockImplementationOnce(() => new Promise((resolve) => { resolveStale = resolve; }))
      .mockResolvedValue({ items: [{ id: 99, title: 'New result' }], total: 1, pages: 1, page: 1, total_applied: 0, avg_score: 0 });

    const { result } = renderHook(() => useJobs());

    await waitFor(() => expect(JobService.getAll).toHaveBeenCalledTimes(1));
    const staleSignal = JobService.getAll.mock.calls[0][1];

    await act(async () => {
      result.current.setFilters({ min_score: 75 });
    });

    expect(staleSignal.aborted).toBe(true);
    await waitFor(() => expect(result.current.jobs).toEqual([{ id: 99, title: 'New result' }]));

    await act(async () => {
      resolveStale({ items: [{ id: 1, title: 'Stale result' }], total: 1, pages: 1, page: 1 });
      await Promise.resolve();
    });

    expect(result.current.jobs).toEqual([{ id: 99, title: 'New result' }]);
    expect(JobService.getAll.mock.calls.some(([requestFilters]) => requestFilters.min_score === 75)).toBe(true);
  });

  it('aborts job and profile requests on unmount', async () => {
    JobService.getAll.mockImplementationOnce(() => new Promise(() => {}));
    SearchService.getProfiles.mockImplementationOnce(() => new Promise(() => {}));
    const { unmount } = renderHook(() => useJobs());

    await waitFor(() => {
      expect(JobService.getAll).toHaveBeenCalledTimes(1);
      expect(SearchService.getProfiles).toHaveBeenCalledTimes(1);
    });
    const jobsSignal = JobService.getAll.mock.calls[0][1];
    const [{ signal: profilesSignal }] = SearchService.getProfiles.mock.calls[0];

    unmount();

    expect(jobsSignal.aborted).toBe(true);
    expect(profilesSignal.aborted).toBe(true);
  });
});
