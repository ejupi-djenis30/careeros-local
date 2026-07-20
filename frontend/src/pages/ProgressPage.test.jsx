import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { ProgressPage } from './ProgressPage';

const mockNavigate = vi.fn();
const mockAddProfileId = vi.fn();
const mockRemoveProfileId = vi.fn();
const mockShowToast = vi.fn();
const mockGetProfiles = vi.fn();

let currentPid = '1';
let currentSearchStatuses = {
  1: { state: 'searching' },
  2: { state: 'analyzing' },
};

vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
  useSearchParams: () => [new URLSearchParams(currentPid ? `pid=${currentPid}` : '')],
}));

vi.mock('../context/SearchContext', () => ({
  useSearchContext: () => ({
    searchStatuses: currentSearchStatuses,
    activeProfileIds: ['1', '2'],
    addProfileId: mockAddProfileId,
    removeProfileId: mockRemoveProfileId,
  }),
}));

vi.mock('../context/ToastContext', () => ({
  useToast: () => ({
    showToast: mockShowToast,
  }),
}));

vi.mock('../services/search', () => ({
  SearchService: {
    getProfiles: (...args) => mockGetProfiles(...args),
  },
}));

vi.mock('../components/SearchProgress', () => ({
  SearchProgress: ({ profileId }) => <div data-testid={`progress-${profileId}`}>Progress {profileId}</div>,
}));

describe('ProgressPage', () => {
  beforeEach(() => {
    currentPid = '1';
    currentSearchStatuses = {
      1: { state: 'searching' },
      2: { state: 'analyzing' },
    };
    mockNavigate.mockReset();
    mockAddProfileId.mockReset();
    mockRemoveProfileId.mockReset();
    mockShowToast.mockReset();
    mockGetProfiles.mockReset();
    mockGetProfiles.mockResolvedValue([
      { id: 1, name: 'Profile 1' },
      { id: 2, name: 'Profile 2' },
    ]);
  });

  it('syncs the visible tab when the pid query parameter changes', async () => {
    const { rerender } = render(<ProgressPage />);

    await waitFor(() => {
      expect(mockAddProfileId).toHaveBeenCalledWith('1');
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Profile 1/i }).className).toContain('btn-primary');
    });

    currentPid = '2';
    rerender(<ProgressPage />);

    await waitFor(() => {
      expect(mockAddProfileId).toHaveBeenCalledWith('2');
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Profile 2/i }).className).toContain('btn-primary');
    });
    expect(screen.getByRole('button', { name: /Profile 1/i }).className).not.toContain('btn-primary');
  });

  it('renders the reserved backend state as a human label', async () => {
    currentSearchStatuses = {
      1: { state: 'reserved' },
      2: { state: 'analyzing' },
    };

    render(<ProgressPage />);

    const reservedTab = await screen.findByRole('button', { name: /Profile 1/i });
    expect(reservedTab).toHaveAttribute('title', 'Status: preparing');
  });
});
