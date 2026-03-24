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
    window.addEventListener('jh_api_error', listener);

    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      status: 500,
      ok: false,
      json: async () => ({ detail: 'Server broke' })
    });

    await expect(ApiClient.get('/jobs/')).rejects.toThrow('Server broke');

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].detail.message).toBe('Server broke');
    window.removeEventListener('jh_api_error', listener);
  });

  it('dispatches a global api error event for failed multipart uploads', async () => {
    const listener = vi.fn();
    window.addEventListener('jh_api_error', listener);

    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      status: 400,
      ok: false,
      json: async () => ({ detail: 'Bad upload' })
    });

    await expect(ApiClient.postMultipart('/search/upload-cv', new FormData())).rejects.toThrow('Bad upload');

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].detail.message).toBe('Bad upload');
    window.removeEventListener('jh_api_error', listener);
  });
});