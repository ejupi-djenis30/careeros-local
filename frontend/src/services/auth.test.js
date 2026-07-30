import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ApiClient } from '../lib/client';
import { AuthService } from './auth';

describe('AuthService', () => {
  beforeEach(() => {
    ApiClient.setToken(null);
    AuthService._refreshPromise = null;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ── login ──────────────────────────────────────────────────────────────────

  it('login sets token when access_token is returned', async () => {
    const postForm = vi.spyOn(ApiClient, 'postForm').mockResolvedValue({
      access_token: 'tok123',
      username: 'alice',
    });
    const result = await AuthService.login('alice', 'pass');
    expect(result.access_token).toBe('tok123');
    expect(ApiClient.getToken()).toBe('tok123');
    expect(postForm).toHaveBeenCalledWith(
      '/auth/login',
      { username: 'alice', password: 'pass' },
      {
        suppressGlobalError: true,
        suppressUnauthorizedRefresh: true,
      },
    );
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

  it('discards a late login response after the session was invalidated', async () => {
    let resolveLogin;
    vi.spyOn(ApiClient, 'postForm').mockReturnValue(new Promise(resolve => {
      resolveLogin = resolve;
    }));
    const login = AuthService.login('alice', 'pass');

    ApiClient.invalidateSession();
    resolveLogin({ access_token: 'late-token', username: 'alice' });

    await expect(login).resolves.toBeNull();
    expect(ApiClient.getToken()).toBeNull();
  });

  // ── register ───────────────────────────────────────────────────────────────

  it('register sets token when access_token is returned', async () => {
    const post = vi.spyOn(ApiClient, 'post').mockResolvedValue({
      access_token: 'new-tok',
      username: 'bob',
    });
    const result = await AuthService.register('bob', 'pass');
    expect(result.access_token).toBe('new-tok');
    expect(ApiClient.getToken()).toBe('new-tok');
    expect(post).toHaveBeenCalledWith(
      '/auth/register',
      { username: 'bob', password: 'pass' },
      {
        suppressGlobalError: true,
        suppressUnauthorizedRefresh: true,
      },
    );
  });

  it('register does not set token when access_token absent', async () => {
    vi.spyOn(ApiClient, 'post').mockResolvedValue({ id: 1 });
    await AuthService.register('bob', 'pass');
    expect(ApiClient.getToken()).toBeNull();
  });

  it('discards a late registration response after the session was invalidated', async () => {
    let resolveRegistration;
    vi.spyOn(ApiClient, 'post').mockReturnValue(new Promise(resolve => {
      resolveRegistration = resolve;
    }));
    const registration = AuthService.register('bob', 'pass');

    ApiClient.invalidateSession();
    resolveRegistration({ access_token: 'late-token', username: 'bob' });

    await expect(registration).resolves.toBeNull();
    expect(ApiClient.getToken()).toBeNull();
  });

  // ── refresh ────────────────────────────────────────────────────────────────

  it('refresh sets token on success', async () => {
    const post = vi.spyOn(ApiClient, 'post').mockResolvedValue({
      access_token: 'refreshed',
      username: 'alice',
    });
    const result = await AuthService.refresh();
    expect(result.access_token).toBe('refreshed');
    expect(ApiClient.getToken()).toBe('refreshed');
    expect(post).toHaveBeenCalledWith('/auth/refresh', {}, {
      suppressGlobalError: true,
      suppressUnauthorizedRefresh: true,
    });
  });

  it('refresh clears token and rethrows on failure', async () => {
    ApiClient.setToken('old-tok');
    vi.spyOn(ApiClient, 'post').mockRejectedValue(new Error('Refresh failed'));
    await expect(AuthService.refresh()).rejects.toThrow('Refresh failed');
    expect(ApiClient.getToken()).toBeNull();
  });

  it('deduplicates overlapping refresh calls', async () => {
    let resolveRefresh;
    const post = vi.spyOn(ApiClient, 'post').mockReturnValue(new Promise(resolve => {
      resolveRefresh = resolve;
    }));

    const first = AuthService.refresh();
    const second = AuthService.refresh();
    expect(post).toHaveBeenCalledTimes(1);
    resolveRefresh({ access_token: 'shared-token', username: 'alice' });

    await expect(Promise.all([first, second])).resolves.toEqual([
      { access_token: 'shared-token', username: 'alice' },
      { access_token: 'shared-token', username: 'alice' },
    ]);
    expect(ApiClient.getToken()).toBe('shared-token');
    expect(AuthService._refreshPromise).toBeNull();
  });

  // ── logout ─────────────────────────────────────────────────────────────────

  it('logout clears token', async () => {
    ApiClient.setToken('active-tok');
    const epoch = ApiClient.getSessionEpoch();
    const post = vi.spyOn(ApiClient, 'post').mockImplementation(async () => {
      expect(ApiClient.getToken()).toBeNull();
      expect(ApiClient.getSessionEpoch()).toBeGreaterThan(epoch);
      return {};
    });
    await AuthService.logout();
    expect(ApiClient.getToken()).toBeNull();
    expect(post).toHaveBeenCalledWith('/auth/logout', {}, {
      suppressGlobalError: true,
      suppressUnauthorizedRefresh: true,
    });
  });

  it('logout clears token even when API call fails', async () => {
    ApiClient.setToken('active-tok');
    vi.spyOn(ApiClient, 'post').mockRejectedValue(new Error('Network'));
    await AuthService.logout();
    expect(ApiClient.getToken()).toBeNull();
  });

  it('keeps refresh and logout unauthorized handling request-scoped when they overlap', async () => {
    ApiClient.setToken('active-token');
    let resolveRefresh;
    const post = vi.spyOn(ApiClient, 'post').mockImplementation((path, _body, options) => {
      expect(options).toEqual({
        suppressGlobalError: true,
        suppressUnauthorizedRefresh: true,
      });
      if (path === '/auth/refresh') {
        return new Promise(resolve => { resolveRefresh = resolve; });
      }
      return Promise.resolve({});
    });

    const refresh = AuthService.refresh();
    await AuthService.logout();
    resolveRefresh({ access_token: 'late-token', username: 'alice' });

    await expect(refresh).resolves.toBeNull();
    expect(post).toHaveBeenCalledTimes(2);
    expect(ApiClient.getToken()).toBeNull();
    expect(AuthService._refreshPromise).toBeNull();
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
