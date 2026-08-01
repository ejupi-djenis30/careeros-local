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
const mockPrepareLogout = vi.fn();
const mockDiscardLogoutToken = vi.fn();

vi.mock('../services/auth', () => ({
  AuthService: {
    refresh: (...args) => mockRefresh(...args),
    login: (...args) => mockLogin(...args),
    register: (...args) => mockRegister(...args),
    logout: (...args) => mockLogout(...args),
    prepareLogout: (...args) => mockPrepareLogout(...args),
    discardLogoutToken: (...args) => mockDiscardLogoutToken(...args),
  },
}));

// ─── Helpers ─────────────────────────────────────────────────────────────────

function Consumer() {
  const { user, isLoggedIn, maintenanceSession, sessionNotice } = useAuth();
  return (
    <>
      <div data-testid="user">{user ?? 'null'}</div>
      <div data-testid="logged-in">{String(isLoggedIn)}</div>
      <div data-testid="maintenance-state">{maintenanceSession?.sessionState ?? 'none'}</div>
      <div data-testid="maintenance-reauth">{String(maintenanceSession?.reauthRequired ?? false)}</div>
      <div data-testid="session-notice">{sessionNotice ?? 'none'}</div>
    </>
  );
}

function PrivateWorkspaceMarker() {
  const { isLoggedIn } = useAuth();
  return isLoggedIn ? <div data-testid="private-workspace">private</div> : null;
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

  it.each(['reset_pending', 'restore_pending', 'erasure_pending'])(
    'keeps the private workspace unmounted when login returns %s',
    async (sessionState) => {
      mockRefresh.mockResolvedValue(null);
      mockLogin.mockResolvedValue({
        access_token: 'maintenance-token',
        session_state: sessionState,
      });

      await renderAndWait(<><Consumer /><PrivateWorkspaceMarker /><LoginButton /></>);
      await act(async () => {
        screen.getByRole('button', { name: 'Login' }).click();
      });

      expect(screen.getByTestId('user')).toHaveTextContent('null');
      expect(screen.getByTestId('logged-in')).toHaveTextContent('false');
      expect(screen.getByTestId('maintenance-state')).toHaveTextContent(sessionState);
      expect(screen.queryByTestId('private-workspace')).toBeNull();
    },
  );

  it('does not let a late normal login replace an active recovery session', async () => {
    let resolveLogin;
    mockRefresh.mockResolvedValue(null);
    mockLogin.mockReturnValue(new Promise((resolve) => {
      resolveLogin = resolve;
    }));
    await renderAndWait(<><Consumer /><PrivateWorkspaceMarker /><LoginButton /></>);

    screen.getByRole('button', { name: 'Login' }).click();
    window.dispatchEvent(new CustomEvent('careeros:maintenance-pending', {
      detail: {
        sessionState: 'erasure_pending',
        reauthRequired: false,
      },
    }));
    await act(async () => resolveLogin({
      access_token: 'late-normal-token',
      username: 'alice',
    }));

    expect(screen.queryByTestId('private-workspace')).toBeNull();
    expect(screen.getByTestId('user')).toHaveTextContent('null');
    expect(screen.getByTestId('maintenance-state')).toHaveTextContent('erasure_pending');
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

  it('keeps the workspace unmounted and offers a retry after explicit logout fails', async () => {
    mockRefresh.mockResolvedValue({ username: 'alice' });
    mockLogout
      .mockRejectedValueOnce(new Error('local backend unavailable'))
      .mockResolvedValueOnce(undefined);

    await renderAndWait(<><Consumer /><LogoutButton /></>);
    await act(async () => {
      screen.getByRole('button', { name: 'Logout' }).click();
    });

    expect(await screen.findByRole('alert')).toHaveTextContent('Session could not be ended');
    expect(screen.queryByTestId('user')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Logout' })).toBeNull();
    const retry = screen.getByRole('button', { name: 'Retry ending session' });
    expect(retry).toBeTruthy();
    await waitFor(() => expect(retry).toHaveFocus());
    expect(mockLogout).toHaveBeenCalledTimes(1);

    await act(async () => {
      screen.getByRole('button', { name: 'Retry ending session' }).click();
    });

    await waitFor(() => expect(mockLogout).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByTestId('user').textContent).toBe('null');
    expect(screen.getByTestId('logged-in').textContent).toBe('false');
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

  it('discards captured authority when forced session cleanup cannot reach the backend', async () => {
    mockRefresh.mockResolvedValue({ username: 'alice' });
    mockLogout.mockRejectedValue(new Error('backend unavailable'));
    await renderAndWait(<><Consumer /><PrivateWorkspaceMarker /></>);

    await act(async () => {
      window.dispatchEvent(new Event('careeros:unauthorized'));
    });

    await waitFor(() => expect(mockDiscardLogoutToken).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId('private-workspace')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('escalates an in-flight normal logout when the session becomes unauthorized', async () => {
    mockRefresh.mockResolvedValue({ username: 'alice' });
    let rejectNormalLogout;
    mockLogout
      .mockImplementationOnce(() => new Promise((_resolve, reject) => {
        rejectNormalLogout = reject;
      }))
      .mockResolvedValueOnce(undefined);
    await renderAndWait(<><Consumer /><PrivateWorkspaceMarker /><LogoutButton /></>);

    await act(async () => {
      screen.getByRole('button', { name: 'Logout' }).click();
    });
    expect(rejectNormalLogout).toBeTypeOf('function');
    act(() => {
      window.dispatchEvent(new Event('careeros:unauthorized'));
    });
    await act(async () => rejectNormalLogout(new Error('first logout failed')));

    await waitFor(() => expect(mockLogout).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId('private-workspace')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(mockDiscardLogoutToken).not.toHaveBeenCalled();
  });

  it('synchronously replaces private DOM with maintenance recovery state', async () => {
    mockRefresh.mockResolvedValue({ username: 'alice' });
    await renderAndWait(<><Consumer /><PrivateWorkspaceMarker /></>);
    expect(screen.getByTestId('private-workspace')).toBeInTheDocument();

    window.dispatchEvent(new CustomEvent('careeros:maintenance-pending', {
      detail: {
        sessionState: 'restore_pending',
        reauthRequired: false,
      },
    }));

    expect(screen.queryByTestId('private-workspace')).toBeNull();
    expect(screen.getByTestId('logged-in')).toHaveTextContent('false');
    expect(screen.getByTestId('maintenance-state')).toHaveTextContent('restore_pending');
    expect(mockLogout).not.toHaveBeenCalled();
  });

  it('keeps private DOM unmounted when a late refresh resolves after maintenance begins', async () => {
    let resolveRefresh;
    mockRefresh.mockReturnValue(new Promise((resolve) => {
      resolveRefresh = resolve;
    }));
    render(<AuthProvider><><Consumer /><PrivateWorkspaceMarker /></></AuthProvider>);

    window.dispatchEvent(new CustomEvent('careeros:maintenance-pending', {
      detail: {
        sessionState: 'reset_pending',
        reauthRequired: true,
      },
    }));
    expect(screen.queryByTestId('private-workspace')).toBeNull();

    await act(async () => resolveRefresh({ username: 'late-user' }));
    expect(screen.queryByTestId('private-workspace')).toBeNull();
    expect(screen.getByTestId('user')).toHaveTextContent('null');
    expect(screen.getByTestId('maintenance-state')).toHaveTextContent('reset_pending');
    expect(screen.getByTestId('maintenance-reauth')).toHaveTextContent('true');
  });

  it('synchronously removes private DOM on recovery completion and preserves a generic notice', async () => {
    mockRefresh.mockResolvedValue({ username: 'alice' });
    await renderAndWait(<><Consumer /><PrivateWorkspaceMarker /></>);
    expect(screen.getByTestId('private-workspace')).toBeInTheDocument();

    window.dispatchEvent(new CustomEvent('careeros:maintenance-complete', {
      detail: { messageKey: 'auth.maintenanceCompleteSignIn' },
    }));

    expect(screen.queryByTestId('private-workspace')).toBeNull();
    await waitFor(() => expect(mockLogout).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId('session-notice')).toHaveTextContent(
      'auth.maintenanceCompleteSignIn',
    );
  });

  it('preserves an explicit restore-complete notice while ending the replaced session', async () => {
    mockRefresh.mockResolvedValue({ username: 'alice' });

    await renderAndWait(<Consumer />);
    await act(async () => {
      window.dispatchEvent(new CustomEvent('careeros:unauthorized', {
        detail: { messageKey: 'auth.restoreCompleteSignIn' },
      }));
    });

    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).toBe('null');
    });
    expect(screen.getByTestId('session-notice').textContent).toBe(
      'auth.restoreCompleteSignIn',
    );
    expect(mockLogout).toHaveBeenCalledTimes(1);
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
