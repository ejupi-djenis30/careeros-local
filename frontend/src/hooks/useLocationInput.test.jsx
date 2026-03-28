import React from 'react';
import { render, screen, act, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useLocationInput } from './useLocationInput';

// ─── Mock ToastContext ────────────────────────────────────────────────────────

const mockShowToast = vi.fn();
vi.mock('../context/ToastContext', () => ({
  useToast: () => ({ showToast: mockShowToast }),
}));

// ─── Thin wrapper component ───────────────────────────────────────────────────

function LocationConsumer({ location, onLocationChange }) {
  const {
    query,
    suggestions,
    isLoading,
    showSuggestions,
    handleSelect,
    handleCurrentLocation,
    setQuery,
  } = useLocationInput(location, onLocationChange);

  return (
    <div>
      <input
        data-testid="input"
        value={query}
        onChange={e => setQuery(e.target.value)}
      />
      <button data-testid="geolocate" onClick={handleCurrentLocation}>
        Use my location
      </button>
      <div data-testid="loading">{String(isLoading)}</div>
      <div data-testid="show-suggestions">{String(showSuggestions)}</div>
      <ul>
        {suggestions.map(s => (
          <li
            key={s.place_id}
            data-testid={`suggestion-${s.place_id}`}
            onClick={() => handleSelect(s)}
          >
            {s.display_name}
          </li>
        ))}
      </ul>
    </div>
  );
}

function renderHook(location = '', onLocationChange = vi.fn()) {
  return render(
    <LocationConsumer location={location} onLocationChange={onLocationChange} />,
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function mockFetchSuccess(data) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue({
    ok: true,
    json: async () => data,
  });
}

function mockFetchFailure(status = 500) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue({
    ok: false,
    status,
    json: async () => ({}),
  });
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('useLocationInput', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  // ── initialisation ──────────────────────────────────────────────────────────

  it('initialises query from the location prop', () => {
    renderHook('Zurich');
    expect(screen.getByTestId('input').value).toBe('Zurich');
  });

  it('updates query when location prop changes', () => {
    const { rerender } = renderHook('Bern');
    rerender(<LocationConsumer location="Basel" onLocationChange={vi.fn()} />);
    expect(screen.getByTestId('input').value).toBe('Basel');
  });

  // ── fetch suggestions (debounced) ───────────────────────────────────────────

  it('does not fetch when query is fewer than 3 characters', async () => {
    const spy = vi.spyOn(globalThis, 'fetch');
    renderHook('');

    await act(async () => {
      await userEvent.type(screen.getByTestId('input'), 'Zu');
      vi.advanceTimersByTime(1100);
    });

    expect(spy).not.toHaveBeenCalled();
  });

  it('fetches OSM suggestions after 1 s debounce', async () => {
    const osmData = [
      {
        place_id: 42,
        display_name: 'Zurich, Canton of Zurich, Switzerland',
        lat: '47.3769',
        lon: '8.5417',
        address: { city: 'Zurich', state: 'Canton of Zurich' },
      },
    ];
    const spy = mockFetchSuccess(osmData);

    const onLocationChange = vi.fn();
    renderHook('', onLocationChange);

    // Simulate debounced typing — change internal query via the input
    await act(async () => {
      await userEvent.clear(screen.getByTestId('input'));
      await userEvent.type(screen.getByTestId('input'), 'Zur');
    });

    await act(async () => {
      vi.advanceTimersByTime(1100);
    });

    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith(
        expect.stringContaining('nominatim.openstreetmap.org/search'),
        expect.any(Object),
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId('suggestion-42')).toBeTruthy();
    });
  });

  it('shows toast when OSM fetch fails with non-abort error', async () => {
    mockFetchFailure(503);

    renderHook('');

    await act(async () => {
      await userEvent.type(screen.getByTestId('input'), 'Geneva');
      vi.advanceTimersByTime(1100);
    });

    await waitFor(() => {
      expect(mockShowToast).toHaveBeenCalledWith(
        expect.stringContaining('location suggestions'),
      );
    });
  });

  // ── handleSelect ────────────────────────────────────────────────────────────

  it('handleSelect updates query and calls onLocationChange with coords', async () => {
    const osmData = [
      {
        place_id: 99,
        // display_name on raw OSM item is overridden by formatOsmSuggestion
        display_name: 'Basel, Switzerland (raw)',
        lat: '47.5596',
        lon: '7.5886',
        // formatOsmSuggestion builds: city + state → "Basel, Basel-Stadt"
        address: { city: 'Basel', state: 'Basel-Stadt' },
      },
    ];
    mockFetchSuccess(osmData);

    const onLocationChange = vi.fn();
    renderHook('', onLocationChange);

    await act(async () => {
      await userEvent.type(screen.getByTestId('input'), 'Bas');
      vi.advanceTimersByTime(1100);
    });

    await waitFor(() => expect(screen.getByTestId('suggestion-99')).toBeTruthy());

    await act(async () => {
      screen.getByTestId('suggestion-99').click();
    });

    expect(screen.getByTestId('input').value).toBe('Basel, Basel-Stadt');
    expect(onLocationChange).toHaveBeenLastCalledWith({
      name: 'Basel, Basel-Stadt',
      lat: 47.5596,
      lon: 7.5886,
    });
    expect(screen.getByTestId('show-suggestions').textContent).toBe('false');
  });

  // ── geolocation ─────────────────────────────────────────────────────────────

  it('shows toast when geolocation is not supported', async () => {
    const originalGeo = navigator.geolocation;
    Object.defineProperty(navigator, 'geolocation', { value: undefined, configurable: true });

    renderHook('');
    await act(async () => { screen.getByTestId('geolocate').click(); });

    expect(mockShowToast).toHaveBeenCalledWith(
      expect.stringContaining('not supported'),
    );

    Object.defineProperty(navigator, 'geolocation', { value: originalGeo, configurable: true });
  });

  it('reverse geocodes current position and calls onLocationChange', async () => {
    const mockGeo = {
      getCurrentPosition: vi.fn((success) => {
        success({ coords: { latitude: 47.3769, longitude: 8.5417 } });
      }),
    };
    Object.defineProperty(navigator, 'geolocation', { value: mockGeo, configurable: true });

    const reverseData = { display_name: 'Zurich City Center, Switzerland' };
    mockFetchSuccess(reverseData);

    const onLocationChange = vi.fn();
    renderHook('', onLocationChange);

    await act(async () => { screen.getByTestId('geolocate').click(); });

    await waitFor(() =>
      expect(screen.getByTestId('input').value).toBe('Zurich City Center, Switzerland'),
    );
    expect(onLocationChange).toHaveBeenCalledWith({
      name: 'Zurich City Center, Switzerland',
      lat: 47.3769,
      lon: 8.5417,
    });
  });

  it('falls back to coordinate string when reverse geocoding fails', async () => {
    const mockGeo = {
      getCurrentPosition: vi.fn((success) => {
        success({ coords: { latitude: 47.3769, longitude: 8.5417 } });
      }),
    };
    Object.defineProperty(navigator, 'geolocation', { value: mockGeo, configurable: true });

    mockFetchFailure(503);

    const onLocationChange = vi.fn();
    renderHook('', onLocationChange);

    await act(async () => { screen.getByTestId('geolocate').click(); });

    await waitFor(() => {
      expect(onLocationChange).toHaveBeenCalledWith(
        expect.objectContaining({ lat: 47.3769, lon: 8.5417 }),
      );
    });
  });

  it('shows toast when geolocation getCurrentPosition errors', async () => {
    const mockGeo = {
      getCurrentPosition: vi.fn((_, error) => {
        error(new Error('permission denied'));
      }),
    };
    Object.defineProperty(navigator, 'geolocation', { value: mockGeo, configurable: true });

    renderHook('');

    await act(async () => { screen.getByTestId('geolocate').click(); });

    await waitFor(() => {
      expect(mockShowToast).toHaveBeenCalledWith(
        expect.stringContaining('Unable to retrieve'),
      );
    });
  });
});
