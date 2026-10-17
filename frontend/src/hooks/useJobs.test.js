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
    dismiss: vi.fn(),
    reactivate: vi.fn(),
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
      expect(consoleSpy).toHaveBeenCalledWith('ui_failure code=jobs_fetch');
      expect(consoleSpy.mock.calls.flat().some((value) => value instanceof Error)).toBe(false);
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
      expect(consoleSpy).toHaveBeenCalledWith('ui_failure code=jobs_profiles');
      expect(consoleSpy.mock.calls.flat().some((value) => value instanceof Error)).toBe(false);
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
  it.each(["dismiss", "undo"])("preserves the current query after a pending %s from another query", async (operation) => {
    let resolveDismiss;
    const pending = new Promise((resolve) => { resolveDismiss = resolve; });
    const first = { id: 1, title: "First query job", dismissed: false };
    const second = { id: 2, title: "Second query job", dismissed: false };
    JobService.getAll.mockImplementation(async ({ search_profile_id }) => ({
      items: [search_profile_id === "B" ? second : first], total: 1, page: 1, pages: 1,
    }));
    JobService.dismiss.mockReturnValue(pending);
    JobService.reactivate.mockResolvedValue(first);
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.jobs).toEqual([first]));
    let write;
    act(() => { write = result.current.dismissJob(first, "not_relevant"); });
    await act(async () => result.current.setFilters({ search_profile_id: "B" }));
    await waitFor(() => expect(result.current.jobs).toEqual([second]));
    await act(async () => { resolveDismiss({ ...first, dismissed: true }); await write; });
    if (operation === "undo") {
      const undo = mockShowToast.mock.calls.find(([message]) => message.messageKey === "jobs.dismissed")[2].onAction;
      await act(async () => undo());
    }
    expect(result.current.jobs).toEqual([second]);
    expect(result.current.pagination.total).toBe(1);
  });

  it("does not duplicate a reactivated job already returned by a refresh", async () => {
    const first = { id: 1, title: "First job", dismissed: false };
    let dismissed = false;
    let resolveUndo;
    JobService.getAll.mockImplementation(async () => ({ items: dismissed ? [] : [first], total: dismissed ? 0 : 1, page: 1, pages: 1 }));
    JobService.dismiss.mockImplementation(async () => { dismissed = true; return { ...first, dismissed: true }; });
    JobService.reactivate.mockReturnValue(new Promise((resolve) => { resolveUndo = resolve; }));
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.jobs).toEqual([first]));
    await act(async () => result.current.dismissJob(first, "not_relevant"));
    const undo = mockShowToast.mock.calls.find(([message]) => message.messageKey === "jobs.dismissed")[2].onAction;
    let pending;
    act(() => { pending = undo(); });
    dismissed = false;
    await act(async () => result.current.fetchJobs());
    await act(async () => { resolveUndo(first); await pending; });
    expect(result.current.jobs).toEqual([first]);
    expect(result.current.pagination.total).toBe(1);
  });

  it("does not report a pending dismissal after unmount", async () => {
    let resolveDismiss;
    JobService.dismiss.mockReturnValue(new Promise((resolve) => { resolveDismiss = resolve; }));
    const { result, unmount } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    let write;
    act(() => { write = result.current.dismissJob(mockJobs[0], "not_relevant"); });
    unmount();
    await act(async () => { resolveDismiss({ ...mockJobs[0], dismissed: true }); await write; });
    expect(mockShowToast).not.toHaveBeenCalled();
  });
  it.each(["dismiss", "undo", "reactivate"])("reports only a fixed code for a failed %s and allows retry", async (operation) => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      const failure = new Error("synthetic-private-value");
      failure.stack = "synthetic-private-stack";
      const first = mockJobs[0];
      const { result } = renderHook(() => useJobs());
      await waitFor(() => expect(result.current.jobs).toEqual(mockJobs));
      let action;
      if (operation === "dismiss") {
        JobService.dismiss.mockReset().mockRejectedValueOnce(failure).mockResolvedValue({ ...first, dismissed: true });
        action = () => result.current.dismissJob(first, "not_relevant");
      } else {
        JobService.reactivate.mockReset().mockRejectedValueOnce(failure).mockResolvedValue(first);
        if (operation === "undo") {
          JobService.dismiss.mockResolvedValue({ ...first, dismissed: true });
          await act(async () => result.current.dismissJob(first, "not_relevant"));
          action = mockShowToast.mock.calls.find(([message]) => message.messageKey === "jobs.dismissed")[2].onAction;
        } else action = () => result.current.reactivateJob(first);
      }
      await act(async () => action());
      expect(consoleSpy).toHaveBeenCalledExactlyOnceWith(`ui_failure code=jobs_${operation}`);
      expect(JSON.stringify(consoleSpy.mock.calls)).not.toContain("synthetic-private");
      expect(result.current.jobs).toEqual(mockJobs);
      await act(async () => action());
      expect(JobService[operation === "dismiss" ? "dismiss" : "reactivate"]).toHaveBeenCalledTimes(2);
    } finally { consoleSpy.mockRestore(); }
  });

  it("retries a failed current-query read after a confirmed dismissal without treating the write as failed", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      JobService.dismiss.mockResolvedValue({ ...mockJobs[0], dismissed: true });
      const { result } = renderHook(() => useJobs());
      await waitFor(() => expect(result.current.jobs).toEqual(mockJobs));
      JobService.getAll.mockRejectedValueOnce(new Error("Synthetic refresh unavailable")).mockResolvedValue({ items: [mockJobs[1]], total: 1, page: 1, pages: 1 });
      await act(async () => result.current.dismissJob(mockJobs[0], "not_relevant"));
      expect(result.current.fetchError).toEqual({ message: "Synthetic refresh unavailable" });
      expect(result.current.jobs).toEqual([mockJobs[1]]);
      expect(mockShowToast.mock.calls.filter(([message]) => message.messageKey === "jobs.dismissed")).toHaveLength(1);
      expect(consoleSpy).toHaveBeenCalledExactlyOnceWith("ui_failure code=jobs_fetch");
      await act(async () => result.current.fetchJobs());
      expect(result.current.fetchError).toBeNull();
      expect(result.current.pagination.total).toBe(1);
    } finally { consoleSpy.mockRestore(); }
  });

  it("keeps a dismissed row when the current query includes dismissed jobs", async () => {
    const first = mockJobs[0];
    const updated = { ...first, dismissed: true };
    JobService.dismiss.mockResolvedValue(updated);
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => result.current.setFilters({ include_dismissed: true }));
    JobService.getAll.mockResolvedValue({ items: [updated, mockJobs[1]], total: 2, page: 1, pages: 1 });
    await act(async () => result.current.dismissJob(first, "not_relevant"));
    expect(result.current.jobs).toEqual([updated, mockJobs[1]]);
    expect(result.current.pagination.total).toBe(2);
  });

  it("reconciles the current page after a pending reactivation from another page", async () => {
    const first = { id: 1, dismissed: true };
    const second = { id: 2, dismissed: false };
    let resolveWrite;
    JobService.getAll.mockImplementation(async ({ page }) => ({ items: [page === 2 ? second : first], total: 2, page, pages: 2 }));
    JobService.reactivate.mockReset().mockReturnValue(new Promise((resolve) => { resolveWrite = resolve; }));
    const { result } = renderHook(() => useJobs());
    await waitFor(() => expect(result.current.jobs).toEqual([first]));
    let pending;
    act(() => { pending = result.current.reactivateJob(first); });
    await act(async () => result.current.setPagination((previous) => ({ ...previous, page: 2 })));
    await waitFor(() => expect(result.current.jobs).toEqual([second]));
    await act(async () => { resolveWrite({ ...first, dismissed: false }); await pending; });
    expect(result.current.jobs).toEqual([second]);
    expect(JobService.getAll).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }), expect.any(AbortSignal));
    expect(result.current.pagination.total).toBe(2);
  });
});
