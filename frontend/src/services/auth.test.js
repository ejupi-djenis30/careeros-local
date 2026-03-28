import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ApiClient } from '../lib/client';
import { AuthService } from './auth';

describe('AuthService', () => {
  beforeEach(() => {
    ApiClient.setToken(null);
    ApiClient._suppressUnauthorized = false;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ── login ──────────────────────────────────────────────────────────────────

  it('login sets token when access_token is returned', async () => {
    vi.spyOn(ApiClient, 'postForm').mockResolvedValue({ access_token: 'tok123', username: 'alice' });
    const result = await AuthService.login('alice', 'pass');
    expect(result.access_token).toBe('tok123');
    expect(ApiClient.getToken()).toBe('tok123');
  });

  it('login does not set token when access_token is absent', async () => {
    vi.spyOn(ApiClient, 'postForm').mockResolvedValue({ error: 'bad creds' });
    await AuthService.login('alice', 'wrong');
    expect(ApiClient.getToken()).toBeNull();
  });

  it('login propagates errors from ApiClient', async () => {
    vi.spyOn(ApiClient, 'postForm').mockRejectedValue(new Error('Network error'));
    await expect(AuthService.login('alice', 'pass')).rejects.toThrow('Network error');
  });

  // ── register ───────────────────────────────────────────────────────────────

  it('register sets token when access_token is returned', async () => {
    vi.spyOn(ApiClient, 'post').mockResolvedValue({ access_token: 'new-tok', username: 'bob' });
    const result = await AuthService.register('bob', 'pass');
    expect(result.access_token).toBe('new-tok');
    expect(ApiClient.getToken()).toBe('new-tok');
  });

  it('register does not set token when access_token absent', async () => {
    vi.spyOn(ApiClient, 'post').mockResolvedValue({ id: 1 });
    await AuthService.register('bob', 'pass');
    expect(ApiClient.getToken()).toBeNull();
  });

  // ── refresh ────────────────────────────────────────────────────────────────

  it('refresh sets token on success', async () => {
    vi.spyOn(ApiClient, 'post').mockResolvedValue({ access_token: 'refreshed', username: 'alice' });
    const result = await AuthService.refresh();
    expect(result.access_token).toBe('refreshed');
    expect(ApiClient.getToken()).toBe('refreshed');
  });

  it('refresh clears token and rethrows on failure', async () => {
    ApiClient.setToken('old-tok');
    vi.spyOn(ApiClient, 'post').mockRejectedValue(new Error('Refresh failed'));
    await expect(AuthService.refresh()).rejects.toThrow('Refresh failed');
    expect(ApiClient.getToken()).toBeNull();
  });

  it('refresh resets _suppressUnauthorized after completion', async () => {
    vi.spyOn(ApiClient, 'post').mockResolvedValue({ access_token: 'tok' });
    await AuthService.refresh();
    expect(ApiClient._suppressUnauthorized).toBe(false);
  });

  it('refresh resets _suppressUnauthorized even on error', async () => {
    vi.spyOn(ApiClient, 'post').mockRejectedValue(new Error('fail'));
    try { await AuthService.refresh(); } catch {}
    expect(ApiClient._suppressUnauthorized).toBe(false);
  });

  // ── logout ─────────────────────────────────────────────────────────────────

  it('logout clears token', async () => {
    ApiClient.setToken('active-tok');
    vi.spyOn(ApiClient, 'post').mockResolvedValue({});
    await AuthService.logout();
    expect(ApiClient.getToken()).toBeNull();
  });

  it('logout clears token even when API call fails', async () => {
    ApiClient.setToken('active-tok');
    vi.spyOn(ApiClient, 'post').mockRejectedValue(new Error('Network'));
    await AuthService.logout();
    expect(ApiClient.getToken()).toBeNull();
  });

  it('logout resets _suppressUnauthorized after completion', async () => {
    vi.spyOn(ApiClient, 'post').mockResolvedValue({});
    await AuthService.logout();
    expect(ApiClient._suppressUnauthorized).toBe(false);
  });

  // ── isLoggedIn ─────────────────────────────────────────────────────────────

  it('isLoggedIn returns false when no token', () => {
    expect(AuthService.isLoggedIn()).toBe(false);
  });

  it('isLoggedIn returns true when token is set', () => {
    ApiClient.setToken('some-token');
    expect(AuthService.isLoggedIn()).toBe(true);
  });
});
