import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AuthProvider, useAuth } from './AuthContext';
import { CAREEROS_BEFORE_LOGOUT_EVENT } from '../lib/events';

// ─── Mock AuthService ────────────────────────────────────────────────────────

const mockRefresh = vi.fn();
const mockLogin = vi.fn();
const mockRegister = vi.fn();
const mockLogout = vi.fn();

vi.mock('../services/auth', () => ({
  AuthService: {
    refresh: (...args) => mockRefresh(...args),
    login: (...args) => mockLogin(...args),
    register: (...args) => mockRegister(...args),
    logout: (...args) => mockLogout(...args),
  },
}));

// ─── Helpers ─────────────────────────────────────────────────────────────────

function Consumer() {
  const { user, isLoggedIn } = useAuth();
  return (
    <>
      <div data-testid="user">{user ?? 'null'}</div>
      <div data-testid="logged-in">{String(isLoggedIn)}</div>
    </>
  );
}

function LoginButton() {
  const { login } = useAuth();
  return (
    <button onClick={() => login('alice', 'pw')}>Login</button>
  );
}

function RegisterButton() {
  const { register } = useAuth();
  return (
    <button onClick={() => register('bob', 'pw')}>Register</button>
  );
}

function LoginWithErrorCapture() {
  const { login } = useAuth();
  const [error, setError] = React.useState(null);

  return (
    <>
      <button onClick={async () => {
        try {
          await login('alice', 'pw');
          setError(null);
        } catch (err) {
          setError(err);
        }
      }}>
        Login With Capture
      </button>
      <div data-testid="login-error">{error?.message || 'none'}</div>
      <div data-testid="login-error-key">{error?.messageKey || 'none'}</div>
    </>
  );
}

function LogoutButton() {
  const { logout } = useAuth();
  return <button onClick={logout}>Logout</button>;
}

function ForcedLogoutBarrier({ waiter }) {
  React.useEffect(() => {
    const holdLogout = (event) => {
      event.preventDefault();
      event.detail?.waitUntil(waiter);
    };
    window.addEventListener(CAREEROS_BEFORE_LOGOUT_EVENT, holdLogout);
    return () => window.removeEventListener(CAREEROS_BEFORE_LOGOUT_EVENT, holdLogout);
  }, [waiter]);
  return null;
}

async function renderAndWait(children) {
  let result;
  await act(async () => {
    result = render(<AuthProvider>{children}</AuthProvider>);
  });
  return result;
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('AuthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLogout.mockResolvedValue(undefined);
  });

  it('shows loading spinner until refresh resolves', async () => {
    let resolveRefresh;
    mockRefresh.mockReturnValue(new Promise(res => { resolveRefresh = res; }));

    render(<AuthProvider><Consumer /></AuthProvider>);

    // Loading spinner should be visible before refresh resolves
    expect(screen.getByRole('status')).toBeTruthy();
    expect(screen.queryByTestId('user')).toBeNull();

    await act(async () => resolveRefresh(null));
    expect(screen.getByTestId('user')).toBeTruthy();
  });

  it('sets user when refresh returns a username', async () => {
    mockRefresh.mockResolvedValue({ username: 'alice' });
    await renderAndWait(<Consumer />);

    expect(screen.getByTestId('user').textContent).toBe('alice');
    expect(screen.getByTestId('logged-in').textContent).toBe('true');
  });

  it('leaves user as null when refresh returns null', async () => {
    mockRefresh.mockResolvedValue(null);
    await renderAndWait(<Consumer />);

    expect(screen.getByTestId('user').textContent).toBe('null');
    expect(screen.getByTestId('logged-in').textContent).toBe('false');
  });

  it('leaves user as null when refresh throws', async () => {
    mockRefresh.mockRejectedValue(new Error('no session'));
    await renderAndWait(<Consumer />);

    expect(screen.getByTestId('user').textContent).toBe('null');
  });

  it('ignores a stale initialization result during StrictMode effect replay', async () => {
    let resolveFirstRefresh;
    let resolveSecondRefresh;
    mockRefresh
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveFirstRefresh = resolve;
      }))
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveSecondRefresh = resolve;
      }));

    render(
      <React.StrictMode>
        <AuthProvider><Consumer /></AuthProvider>
      </React.StrictMode>,
    );
    await waitFor(() => expect(mockRefresh).toHaveBeenCalledTimes(2));

    await act(async () => resolveSecondRefresh(null));
    expect(screen.getByTestId('user').textContent).toBe('null');
    expect(screen.getByTestId('logged-in').textContent).toBe('false');

    await act(async () => resolveFirstRefresh({ username: 'stale-user' }));
    expect(screen.getByTestId('user').textContent).toBe('null');
    expect(screen.getByTestId('logged-in').textContent).toBe('false');
  });

  it('login sets user and returns response', async () => {
    mockRefresh.mockResolvedValue(null);
    mockLogin.mockResolvedValue({ access_token: 'tok' });

    await renderAndWait(<><Consumer /><LoginButton /></>);

    await act(async () => {
      screen.getByRole('button').click();
    });

    expect(mockLogin).toHaveBeenCalledWith('alice', 'pw');
    expect(screen.getByTestId('user').textContent).toBe('alice');
    expect(screen.getByTestId('logged-in').textContent).toBe('true');
  });

  it('login surfaces an explicit error when response has no access_token', async () => {
    mockRefresh.mockResolvedValue(null);
    mockLogin.mockResolvedValue({ error: 'invalid credentials' });

    await renderAndWait(<><Consumer /><LoginWithErrorCapture /></>);

    await act(async () => {
      screen.getByRole('button', { name: 'Login With Capture' }).click();
    });

    expect(screen.getByTestId('user').textContent).toBe('null');
    expect(screen.getByTestId('login-error').textContent).toBe('invalid credentials');
    expect(screen.getByTestId('login-error-key').textContent).toBe('none');
  });

  it('marks a fallback authentication error for live translation', async () => {
    mockRefresh.mockResolvedValue(null);
    mockLogin.mockResolvedValue({});

    await renderAndWait(<LoginWithErrorCapture />);

    await act(async () => {
      screen.getByRole('button', { name: 'Login With Capture' }).click();
    });

    expect(screen.getByTestId('login-error').textContent).toBe('Login failed. Please try again.');
    expect(screen.getByTestId('login-error-key').textContent).toBe('auth.loginFailed');
  });

  it('register sets user and returns response', async () => {
    mockRefresh.mockResolvedValue(null);
    mockRegister.mockResolvedValue({ access_token: 'tok2' });

    await renderAndWait(<><Consumer /><RegisterButton /></>);

    await act(async () => {
      screen.getByRole('button').click();
    });

    expect(mockRegister).toHaveBeenCalledWith('bob', 'pw');
    expect(screen.getByTestId('user').textContent).toBe('bob');
  });

  it('logout clears user', async () => {
    mockRefresh.mockResolvedValue({ username: 'alice' });

    await renderAndWait(<><Consumer /><LogoutButton /></>);

    expect(screen.getByTestId('user').textContent).toBe('alice');

    await act(async () => {
      screen.getByRole('button').click();
    });

    expect(mockLogout).toHaveBeenCalled();
    expect(screen.getByTestId('user').textContent).toBe('null');
  });

  it('does not expose login controls until the server logout has finished', async () => {
    mockRefresh.mockResolvedValue({ username: 'alice' });
    let resolveLogout;
    mockLogout.mockReturnValue(new Promise((resolve) => {
      resolveLogout = resolve;
    }));

    await renderAndWait(<><Consumer /><LoginButton /><LogoutButton /></>);
    await act(async () => {
      screen.getByRole('button', { name: 'Logout' }).click();
    });

    expect(screen.getByRole('status')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Login' })).toBeNull();
    expect(screen.queryByTestId('user')).toBeNull();
    expect(mockLogout).toHaveBeenCalledTimes(1);

    await act(async () => resolveLogout());
    expect(screen.getByTestId('user').textContent).toBe('null');
    expect(screen.getByRole('button', { name: 'Login' })).toBeTruthy();
  });

  it('lets an in-flight sensitive operation cancel a normal logout', async () => {
    mockRefresh.mockResolvedValue({ username: 'alice' });
    const preventLogout = event => event.preventDefault();
    window.addEventListener('careeros:before-logout', preventLogout);

    await renderAndWait(<><Consumer /><LogoutButton /></>);
    await act(async () => {
      screen.getByRole('button').click();
    });

    expect(mockLogout).not.toHaveBeenCalled();
    expect(screen.getByTestId('user').textContent).toBe('alice');
    window.removeEventListener('careeros:before-logout', preventLogout);
  });

  it('handles the CareerOS unauthorized event by calling logout', async () => {
    mockRefresh.mockResolvedValue({ username: 'alice' });

    await renderAndWait(<Consumer />);
    expect(screen.getByTestId('user').textContent).toBe('alice');

    await act(async () => {
      window.dispatchEvent(new Event('careeros:unauthorized'));
    });

    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).toBe('null');
    });
    expect(mockLogout).toHaveBeenCalled();
  });

  it('waits for forced-logout cleanup before invalidating the server session', async () => {
    mockRefresh.mockResolvedValue({ username: 'alice' });
    let releaseCleanup;
    const cleanup = new Promise((resolve) => {
      releaseCleanup = resolve;
    });

    await renderAndWait(
      <>
        <Consumer />
        <ForcedLogoutBarrier waiter={cleanup} />
      </>,
    );
    await act(async () => {
      window.dispatchEvent(new Event('careeros:unauthorized'));
    });

    expect(screen.getByRole('status')).toBeTruthy();
    expect(mockLogout).not.toHaveBeenCalled();

    await act(async () => releaseCleanup());
    await waitFor(() => expect(mockLogout).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId('user').textContent).toBe('null');
  });

  it('useAuth throws when used outside AuthProvider', () => {
    const OriginalConsoleError = console.error;
    console.error = vi.fn(); // suppress React boundary noise
    function Orphan() {
      useAuth();
      return null;
    }
    expect(() => render(<Orphan />)).toThrow('useAuth must be used within an AuthProvider');
    console.error = OriginalConsoleError;
  });
});
