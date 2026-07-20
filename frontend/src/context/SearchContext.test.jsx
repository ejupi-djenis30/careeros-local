import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SearchProvider, useSearchContext } from './SearchContext';

const mockGetAllStatuses = vi.fn();

vi.mock('../services/search', () => ({
  SearchService: {
    getAllStatuses: (...args) => mockGetAllStatuses(...args)
  }
}));

function Consumer() {
  const { activeProfileIds, searchStatuses, statusHeartbeat } = useSearchContext();
  return (
    <>
      <div data-testid="active-ids">{activeProfileIds.join(',')}</div>
      <div data-testid="status-state">{searchStatuses['1']?.state || 'none'}</div>
      <div data-testid="status-heartbeat">{statusHeartbeat}</div>
    </>
  );
}

async function flushAsyncWork() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe('SearchContext', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockGetAllStatuses.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('tracks active profiles and backs off polling after terminal states', async () => {
    mockGetAllStatuses
      .mockResolvedValueOnce({ 1: { state: 'searching' } })
      .mockResolvedValueOnce({ 1: { state: 'done' } })
      .mockResolvedValue({});

    render(
      <SearchProvider>
        <Consumer />
      </SearchProvider>
    );

    await flushAsyncWork();

    await waitFor(() => {
      expect(screen.getByTestId('active-ids')).toHaveTextContent('1');
      expect(screen.getByTestId('status-state')).toHaveTextContent('searching');
      expect(screen.getByTestId('status-heartbeat')).toHaveTextContent('1');
    });

    expect(mockGetAllStatuses).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(1500);
    });

    await flushAsyncWork();

    await waitFor(() => {
      expect(screen.getByTestId('active-ids')).toHaveTextContent('');
      expect(screen.getByTestId('status-state')).toHaveTextContent('done');
      expect(screen.getByTestId('status-heartbeat')).toHaveTextContent('2');
    });

    expect(mockGetAllStatuses).toHaveBeenCalledTimes(2);

    await act(async () => {
      vi.advanceTimersByTime(14000);
    });

    expect(mockGetAllStatuses).toHaveBeenCalledTimes(2);

    await act(async () => {
      vi.advanceTimersByTime(1000);
    });

    await waitFor(() => {
      expect(mockGetAllStatuses).toHaveBeenCalledTimes(3);
    });
  });

  it('aborts the active poll when the authenticated provider unmounts', async () => {
    let requestSignal;
    mockGetAllStatuses.mockImplementation((signal) => {
      requestSignal = signal;
      return new Promise((resolve, reject) => {
        signal.addEventListener('abort', () => {
          reject(Object.assign(new Error('Aborted'), { name: 'AbortError' }));
        }, { once: true });
      });
    });

    const { unmount } = render(
      <SearchProvider>
        <Consumer />
      </SearchProvider>
    );

    await waitFor(() => {
      expect(requestSignal).toBeInstanceOf(AbortSignal);
    });

    unmount();

    expect(requestSignal.aborted).toBe(true);
  });

  it('does not increment heartbeat when a poll returns unchanged statuses', async () => {
    mockGetAllStatuses
      .mockResolvedValueOnce({ 1: { state: 'searching', log: ['tick'] } })
      .mockResolvedValueOnce({ 1: { state: 'searching', log: ['tick'] } });

    render(
      <SearchProvider>
        <Consumer />
      </SearchProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('status-heartbeat')).toHaveTextContent('1');
    });

    await act(async () => {
      vi.advanceTimersByTime(1500);
    });

    await flushAsyncWork();

    await waitFor(() => {
      expect(screen.getByTestId('status-heartbeat')).toHaveTextContent('1');
    });
  });

  it('treats reserved statuses as active while the background task is still starting', async () => {
    mockGetAllStatuses.mockResolvedValue({ 1: { state: 'reserved' } });

    render(
      <SearchProvider>
        <Consumer />
      </SearchProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('active-ids')).toHaveTextContent('1');
      expect(screen.getByTestId('status-state')).toHaveTextContent('reserved');
    });
  });
});

// ── Ghost-PID TTL tests ────────────────────────────────────────────────────────

function ConsumerWithAdd() {
  const { activeProfileIds, addProfileId, removeProfileId } = useSearchContext();
  return (
    <>
      <div data-testid="active-ids">{activeProfileIds.join(',')}</div>
      <button data-testid="add-42" onClick={() => addProfileId(42)}>add</button>
      <button data-testid="remove-42" onClick={() => removeProfileId(42)}>remove</button>
    </>
  );
}

describe('SearchContext — ghost PID TTL', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockGetAllStatuses.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('locally added pid is preserved during TTL window when server has not confirmed it', async () => {
    // Server never returns pid 42
    mockGetAllStatuses.mockResolvedValue({});

    const { getByTestId } = render(
      <SearchProvider>
        <ConsumerWithAdd />
      </SearchProvider>
    );

    await flushAsyncWork();

    // Locally add pid 42
    await act(async () => {
      getByTestId('add-42').click();
    });

    // Advance 15s (<< 30s TTL) to trigger a slow-poll cycle while still within the window
    await act(async () => {
      vi.advanceTimersByTime(15001);
    });
    await flushAsyncWork();

    // pid 42 should still be in the list — server hasn't confirmed it yet, but TTL hasn't expired
    expect(getByTestId('active-ids').textContent).toBe('42');
  });

  it('locally added pid is dropped after TTL when server never confirms it', async () => {
    const listener = vi.fn();
    window.addEventListener('careeros:api-error', listener);

    // Server never returns pid 42
    mockGetAllStatuses.mockResolvedValue({});

    const { getByTestId } = render(
      <SearchProvider>
        <ConsumerWithAdd />
      </SearchProvider>
    );

    await flushAsyncWork();

    // Locally add pid 42 immediately after first poll
    await act(async () => {
      getByTestId('add-42').click();
    });

    // Advance well past TTL (30s + margin)
    await act(async () => {
      vi.advanceTimersByTime(35000);
    });
    await flushAsyncWork();

    // Trigger another poll cycle so the TTL check runs
    await act(async () => {
      vi.advanceTimersByTime(15001);
    });
    await flushAsyncWork();

    await waitFor(() => {
      expect(getByTestId('active-ids').textContent).toBe('');
    });

    expect(listener).toHaveBeenCalledWith(
      expect.objectContaining({
        detail: expect.objectContaining({
          messageKey: 'searchStatus.startFailed',
          variables: { id: '42' },
        })
      })
    );

    window.removeEventListener('careeros:api-error', listener);
  });

  it('locally added pid is retained permanently once server confirms it', async () => {
    // First poll: server confirms pid 42 is running
    mockGetAllStatuses.mockResolvedValue({ 42: { state: 'searching' } });

    const { getByTestId } = render(
      <SearchProvider>
        <ConsumerWithAdd />
      </SearchProvider>
    );

    await flushAsyncWork();

    await waitFor(() => {
      expect(getByTestId('active-ids').textContent).toBe('42');
    });

    // Advance well past TTL — confirmed ID must survive
    await act(async () => {
      vi.advanceTimersByTime(60000);
    });
    await flushAsyncWork();

    // Server still returns pid 42 as running
    expect(getByTestId('active-ids').textContent).toBe('42');
  });

  it('removeProfileId clears the pending-TTL entry', async () => {
    mockGetAllStatuses.mockResolvedValue({});

    const { getByTestId } = render(
      <SearchProvider>
        <ConsumerWithAdd />
      </SearchProvider>
    );

    await flushAsyncWork();

    await act(async () => {
      getByTestId('add-42').click();
    });

    expect(getByTestId('active-ids').textContent).toBe('42');

    await act(async () => {
      getByTestId('remove-42').click();
    });

    expect(getByTestId('active-ids').textContent).toBe('');
  });
});
