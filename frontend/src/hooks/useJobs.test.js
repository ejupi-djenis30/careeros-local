import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useJobs } from './useJobs';
import { JobService } from '../services/jobs';
import { SearchService } from '../services/search';

let mockActiveProfileIds = [];
let mockStatusHeartbeat = 0;
const { mockShowToast } = vi.hoisted(() => ({ mockShowToast: vi.fn() }));

vi.mock('../services/jobs', () => ({
  JobService: {
    getAll: vi.fn(),
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
    getProfileSummaries: vi.fn(),
  }
}));

vi.mock('../context/ToastContext', () => ({
  useToast: () => ({ showToast: mockShowToast, clearToast: vi.fn() })
}));

describe('useJobs', () => {
  const mockJobs = [
    { id: 1, title: 'Job 1', application_id: null },
    { id: 2, title: 'Job 2', application_id: 'application-2', application_stage: 'applied' },
  ];

  const mockPagination = {
    items: mockJobs,
    total: 2,
    pages: 1,
    page: 1,
    total_tracked: 1,
    total_applied: 1,
    avg_score: 80
  };

  const mockProfiles = [{ id: 1, name: 'Profile 1' }];

  beforeEach(() => {
    vi.clearAllMocks();
    mockActiveProfileIds = [];
    mockStatusHeartbeat = 0;
    JobService.getAll.mockResolvedValue(mockPagination);
    SearchService.getProfileSummaries.mockResolvedValue(mockProfiles);
  });

  it('fetches jobs and profiles on mount', async () => {
    const { result } = renderHook(() => useJobs());

    await waitFor(() => {
      expect(result.current.jobs).toEqual(mockJobs);
      expect(result.current.searchProfiles).toEqual(mockProfiles);
      expect(result.current.isLoading).toBe(false);
    });
  });

  it('keeps the tracked application total returned by the backend', async () => {
    const { result } = renderHook(() => useJobs());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.pagination.total_tracked).toBe(1);
  });

  it('keeps a null tracked total so older responses can use the applied fallback', async () => {
    JobService.getAll.mockResolvedValue({
      ...mockPagination,
      total_tracked: undefined,
      total_applied: 2,
    });
    const { result } = renderHook(() => useJobs());

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.pagination.total_tracked).toBeNull();
    expect(result.current.pagination.total_applied).toBe(2);
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

  it('keeps fallback fetch errors as localization metadata', async () => {
    const error = new Error();
    error.name = 'NetworkError';
    JobService.getAll.mockRejectedValue(error);

    const { result } = renderHook(() => useJobs());

    await waitFor(() => {
      expect(result.current.fetchError).toEqual({ messageKey: 'jobs.error.load' });
    });
  });

  it('logs error on profile summary failure', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    SearchService.getProfileSummaries.mockRejectedValue(new Error('PROFILE ERROR'));

    renderHook(() => useJobs());

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalledWith('Failed to load search profiles', expect.any(Error));
    });
    expect(mockShowToast).toHaveBeenCalledWith({ message: 'PROFILE ERROR' });
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
    SearchService.getProfileSummaries.mockImplementationOnce(() => new Promise(() => {}));
    const { unmount } = renderHook(() => useJobs());

    await waitFor(() => {
      expect(JobService.getAll).toHaveBeenCalledTimes(1);
      expect(SearchService.getProfileSummaries).toHaveBeenCalledTimes(1);
    });
    const jobsSignal = JobService.getAll.mock.calls[0][1];
    const [{ signal: profilesSignal }] = SearchService.getProfileSummaries.mock.calls[0];

    unmount();

    expect(jobsSignal.aborted).toBe(true);
    expect(profilesSignal.aborted).toBe(true);
  });
});
