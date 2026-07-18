import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AuthProvider, useAuth } from './AuthContext';

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
  const [error, setError] = React.useState('');

  return (
    <>
      <button onClick={async () => {
        try {
          await login('alice', 'pw');
          setError('');
        } catch (err) {
          setError(err.message);
        }
      }}>
        Login With Capture
      </button>
      <div data-testid="login-error">{error || 'none'}</div>
    </>
  );
}

function LogoutButton() {
  const { logout } = useAuth();
  return <button onClick={logout}>Logout</button>;
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
