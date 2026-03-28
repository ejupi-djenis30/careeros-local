import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ApiClient } from './client';

describe('ApiClient — extended coverage', () => {
  beforeEach(() => {
    ApiClient.setToken(null);
    ApiClient._refreshPromise = null;
    ApiClient._suppressUnauthorized = false;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ── Token management ────────────────────────────────────────────────────────

  it('setToken / getToken round-trip', () => {
    ApiClient.setToken('abc123');
    expect(ApiClient.getToken()).toBe('abc123');
  });

  it('setToken(null) clears token', () => {
    ApiClient.setToken('tok');
    ApiClient.setToken(null);
    expect(ApiClient.getToken()).toBeNull();
  });

  it('getHeaders includes Authorization when token is set', () => {
    ApiClient.setToken('my-token');
    const headers = ApiClient.getHeaders();
    expect(headers['Authorization']).toBe('Bearer my-token');
  });

  it('getHeaders has no Authorization when token is null', () => {
    const headers = ApiClient.getHeaders();
    expect(headers['Authorization']).toBeUndefined();
  });

  // ── Successful requests ─────────────────────────────────────────────────────

  it('get returns parsed JSON on 200', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({ data: 'ok' }),
    });
    const result = await ApiClient.get('/some/path');
    expect(result).toEqual({ data: 'ok' });
  });

  it('post sends JSON body and returns parsed response', async () => {
    const mockFetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({ created: true }),
    });
    const result = await ApiClient.post('/items', { name: 'test' });
    expect(result).toEqual({ created: true });
    const callBody = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(callBody).toEqual({ name: 'test' });
  });

  it('patch sends JSON body', async () => {
    const mockFetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({ updated: true }),
    });
    await ApiClient.patch('/items/1', { applied: true });
    const callBody = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(callBody).toEqual({ applied: true });
  });

  it('delete sends DELETE method', async () => {
    const mockFetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({}),
    });
    await ApiClient.delete('/items/1');
    expect(mockFetch.mock.calls[0][1].method).toBe('DELETE');
  });

  it('postForm sends form-encoded body', async () => {
    const mockFetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({ access_token: 'tok' }),
    });
    await ApiClient.postForm('/auth/login', { username: 'a', password: 'b' });
    const body = mockFetch.mock.calls[0][1].body;
    // body is a URLSearchParams object; serialise before asserting
    const serialised = body.toString();
    expect(serialised).toContain('username=a');
    expect(serialised).toContain('password=b');
  });

  // ── Error extraction ────────────────────────────────────────────────────────

  it('uses detail string from error body', async () => {
    const listener = vi.fn();
    window.addEventListener('jh_api_error', listener);
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      status: 400,
      ok: false,
      json: async () => ({ detail: 'Bad request' }),
    });
    await expect(ApiClient.get('/bad')).rejects.toThrow('Bad request');
    expect(listener.mock.calls[0][0].detail.message).toBe('Bad request');
    window.removeEventListener('jh_api_error', listener);
  });

  it('joins array detail messages', async () => {
    const listener = vi.fn();
    window.addEventListener('jh_api_error', listener);
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      status: 422,
      ok: false,
      json: async () => ({ detail: [{ msg: 'field required' }, { msg: 'invalid value' }] }),
    });
    await expect(ApiClient.get('/validate')).rejects.toThrow('field required, invalid value');
    window.removeEventListener('jh_api_error', listener);
  });

  it('falls back to message field when detail absent', async () => {
    const listener = vi.fn();
    window.addEventListener('jh_api_error', listener);
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      status: 500,
      ok: false,
      json: async () => ({ message: 'Internal error' }),
    });
    await expect(ApiClient.get('/fail')).rejects.toThrow('Internal error');
    window.removeEventListener('jh_api_error', listener);
  });

  // ── Unauthorised / refresh flow ─────────────────────────────────────────────

  it('dispatches jh_unauthorized when refresh fails', async () => {
    const listener = vi.fn();
    window.addEventListener('jh_unauthorized', listener);

    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce({ status: 401, ok: false, json: async () => ({}) })
      .mockResolvedValueOnce({ ok: false });  // refresh fails

    await expect(ApiClient.get('/protected')).rejects.toThrow();
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener('jh_unauthorized', listener);
  });

  it('retries original request after successful refresh', async () => {
    ApiClient.setToken('old-token');
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce({ status: 401, ok: false, json: async () => ({}) })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ access_token: 'new-token' }),
      })
      .mockResolvedValueOnce({ status: 200, ok: true, json: async () => ({ data: 'retried' }) });

    const result = await ApiClient.get('/protected');
    expect(result).toEqual({ data: 'retried' });
    expect(ApiClient.getToken()).toBe('new-token');
  });
});
