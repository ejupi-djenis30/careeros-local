import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ApiClient } from './client';

describe('ApiClient', () => {
  beforeEach(() => {
    ApiClient.setToken(null);
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

  it('skips refresh and preserves the server error for an authentication request', async () => {
    ApiClient.setToken('old-tok');

    const handleUnauthorizedSpy = vi.spyOn(ApiClient, '_handleUnauthorized');
    const unauthorizedListener = vi.fn();
    window.addEventListener('careeros:unauthorized', unauthorizedListener);

    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      status: 401,
      ok: false,
      clone() { return this; },
      json: async () => ({ detail: 'Incorrect username or password' }),
    });

    await expect(ApiClient.post('/auth/login', {}, {
      suppressGlobalError: true,
      suppressUnauthorizedRefresh: true,
    })).rejects.toThrow('Incorrect username or password');

    // Must NOT attempt the full refresh + event cycle
    expect(handleUnauthorizedSpy).not.toHaveBeenCalled();
    expect(unauthorizedListener).not.toHaveBeenCalled();

    window.removeEventListener('careeros:unauthorized', unauthorizedListener);
  });

  it('dispatches the CareerOS unauthorized event when refresh fails', async () => {
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

  it('does not log out globally when a caller cancels during a successful refresh', async () => {
    ApiClient.setToken('old-token');
    const caller = new AbortController();
    const unauthorizedListener = vi.fn();
    window.addEventListener('careeros:unauthorized', unauthorizedListener);
    let resolveRefresh;
    const refreshResponse = new Promise((resolve) => {
      resolveRefresh = resolve;
    });
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce({ status: 401, ok: false })
      .mockImplementationOnce(() => refreshResponse);

    const request = ApiClient.get('/some/api', caller.signal);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    caller.abort();
    resolveRefresh({
      status: 200,
      ok: true,
      json: async () => ({ access_token: 'refreshed-token' }),
    });

    await expect(request).rejects.toMatchObject({ name: 'AbortError' });
    expect(ApiClient.getToken()).toBe('refreshed-token');
    expect(unauthorizedListener).not.toHaveBeenCalled();
    window.removeEventListener('careeros:unauthorized', unauthorizedListener);
  });

  it('does not restore a session or retry after logout invalidates a pending refresh', async () => {
    ApiClient.setToken('old-token');
    let resolveRefresh;
    const refreshResponse = new Promise((resolve) => {
      resolveRefresh = resolve;
    });
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce({ status: 401, ok: false })
      .mockImplementationOnce(() => refreshResponse)
      .mockResolvedValueOnce({
        status: 201,
        ok: true,
        json: async () => ({ grant: { id: 'must-not-exist' } }),
      });

    const request = ApiClient.post('/automation/grants', {
      label: 'Must not be retried',
    });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    ApiClient.invalidateSession();
    resolveRefresh({
      status: 200,
      ok: true,
      json: async () => ({ access_token: 'late-token' }),
    });

    await expect(request).rejects.toThrow('SESSION_CHANGED');
    expect(ApiClient.getToken()).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('normalizes a fetch abort reason when logout invalidates an active request', async () => {
    ApiClient.setToken('active-token');
    vi.spyOn(globalThis, 'fetch').mockImplementation((_url, { signal }) => (
      new Promise((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(signal.reason), { once: true });
      })
    ));

    const request = ApiClient.get('/automation/grants');
    await vi.waitFor(() => expect(ApiClient._activeControllers.size).toBe(1));
    ApiClient.invalidateSession();

    await expect(request).rejects.toMatchObject({
      name: 'ApiError',
      message: 'SESSION_CHANGED',
      status: 0,
    });
    expect(ApiClient._activeControllers.size).toBe(0);
  });

  it('rejects a slow JSON body that finishes after session invalidation', async () => {
    ApiClient.setToken('active-token');
    let resolveBody;
    const body = new Promise((resolve) => {
      resolveBody = resolve;
    });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      status: 200,
      ok: true,
      json: () => body,
    });

    const request = ApiClient.get('/automation/grants');
    await vi.waitFor(() => expect(ApiClient._activeControllers.size).toBe(1));
    ApiClient.invalidateSession();
    expect(ApiClient._activeControllers.size).toBe(1);
    resolveBody([{ id: 'late-grant' }]);

    await expect(request).rejects.toThrow('SESSION_CHANGED');
    expect(ApiClient.getToken()).toBeNull();
    expect(ApiClient._activeControllers.size).toBe(0);
  });

  it('does not dispatch a stale non-OK response after the session changes', async () => {
    ApiClient.setToken('active-token');
    const listener = vi.fn();
    window.addEventListener('careeros:api-error', listener);
    let resolveErrorBody;
    const errorBody = new Promise((resolve) => {
      resolveErrorBody = resolve;
    });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      status: 409,
      ok: false,
      clone() { return this; },
      json: () => errorBody,
    });

    const request = ApiClient.post('/automation/grants', {
      label: 'stale response',
    });
    await vi.waitFor(() => expect(ApiClient._activeControllers.size).toBe(1));
    ApiClient.invalidateSession();
    resolveErrorBody({
      detail: {
        code: 'active_grant_limit',
        message: 'This message belongs to the old session',
      },
    });

    await expect(request).rejects.toThrow('SESSION_CHANGED');
    expect(listener).not.toHaveBeenCalled();
    window.removeEventListener('careeros:api-error', listener);
  });
});
