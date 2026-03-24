import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SearchProvider, useSearchContext } from './SearchContext';

const mockGetAllStatuses = vi.fn();
const mockAuthState = { isLoggedIn: true };

vi.mock('../services/search', () => ({
  SearchService: {
    getAllStatuses: (...args) => mockGetAllStatuses(...args)
  }
}));

vi.mock('./AuthContext', () => ({
  useAuth: () => mockAuthState
}));

function Consumer() {
  const { activeProfileIds, searchStatuses } = useSearchContext();
  return (
    <>
      <div data-testid="active-ids">{activeProfileIds.join(',')}</div>
      <div data-testid="status-state">{searchStatuses['1']?.state || 'none'}</div>
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
    mockAuthState.isLoggedIn = true;
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
    });

    expect(mockGetAllStatuses).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(1500);
    });

    await flushAsyncWork();

    await waitFor(() => {
      expect(screen.getByTestId('active-ids')).toHaveTextContent('');
      expect(screen.getByTestId('status-state')).toHaveTextContent('done');
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

  it('clears local state when the user is logged out', async () => {
    mockGetAllStatuses.mockResolvedValue({ 1: { state: 'searching' } });

    const { rerender } = render(
      <SearchProvider>
        <Consumer />
      </SearchProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('active-ids')).toHaveTextContent('1');
    });

    mockAuthState.isLoggedIn = false;

    rerender(
      <SearchProvider>
        <Consumer />
      </SearchProvider>
    );

    await flushAsyncWork();

    await flushAsyncWork();

    await waitFor(() => {
      expect(screen.getByTestId('active-ids')).toHaveTextContent('');
      expect(screen.getByTestId('status-state')).toHaveTextContent('none');
    });
  });
});