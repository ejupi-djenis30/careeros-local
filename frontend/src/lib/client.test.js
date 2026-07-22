import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ApiClient } from './client';

describe('ApiClient', () => {
  beforeEach(() => {
    ApiClient.setToken(null);
    ApiClient._suppressUnauthorized = false;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('dispatches a global api error event for failed JSON requests', async () => {
    const listener = vi.fn();
    window.addEventListener('careeros:api-error', listener);

    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      status: 500,
      ok: false,
      json: async () => ({ detail: 'Server broke' })
    });

    await expect(ApiClient.get('/jobs/')).rejects.toThrow('Server broke');

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].detail.message).toBe('Server broke');
    window.removeEventListener('careeros:api-error', listener);
  });

  it('uses the message from a structured API detail instead of serializing JSON into the UI', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      status: 428,
      ok: false,
      clone() { return this; },
      json: async () => ({ detail: { code: 'local_model_required', message: 'Local model setup required' } }),
    });

    const request = ApiClient.post('/search/start', {}, { suppressGlobalError: true });
    await expect(request).rejects.toMatchObject({
      status: 428,
      message: 'Local model setup required',
      details: { detail: { code: 'local_model_required' } },
    });
  });

  it('dispatches a global api error event for failed multipart uploads', async () => {
    const listener = vi.fn();
    window.addEventListener('careeros:api-error', listener);

    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      status: 400,
      ok: false,
      json: async () => ({ detail: 'Bad upload' })
    });

    await expect(ApiClient.postMultipart('/search/upload-cv', new FormData())).rejects.toThrow('Bad upload');

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].detail.message).toBe('Bad upload');
    window.removeEventListener('careeros:api-error', listener);
  });

  // ── _suppressUnauthorized ──────────────────────────────────────────────────

  it('skips refresh and throws UNAUTHORIZED immediately when _suppressUnauthorized is true', async () => {
    ApiClient._suppressUnauthorized = true;
    ApiClient.setToken('old-tok');

    const handleUnauthorizedSpy = vi.spyOn(ApiClient, '_handleUnauthorized');
    const unauthorizedListener = vi.fn();
    window.addEventListener('careeros:unauthorized', unauthorizedListener);

    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      status: 401,
      ok: false,
    });

    await expect(ApiClient.get('/auth/refresh')).rejects.toThrow('UNAUTHORIZED');

    // Must NOT attempt the full refresh + event cycle
    expect(handleUnauthorizedSpy).not.toHaveBeenCalled();
    expect(unauthorizedListener).not.toHaveBeenCalled();

    window.removeEventListener('careeros:unauthorized', unauthorizedListener);
  });

  it('dispatches the CareerOS unauthorized event when refresh fails', async () => {
    ApiClient._suppressUnauthorized = false;
    ApiClient.setToken('old-tok');

    const unauthorizedListener = vi.fn();
    window.addEventListener('careeros:unauthorized', unauthorizedListener);

    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce({ status: 401, ok: false }) // original request → 401
      .mockResolvedValueOnce({ status: 401, ok: false }); // refresh attempt → also 401

    await expect(ApiClient.get('/some/api')).rejects.toThrow('UNAUTHORIZED');

    expect(unauthorizedListener).toHaveBeenCalledTimes(1);

    window.removeEventListener('careeros:unauthorized', unauthorizedListener);
  });
});
