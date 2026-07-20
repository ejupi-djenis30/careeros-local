import React from 'react';
import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ToastProvider } from './ToastContext';
import { I18nProvider } from '../i18n/I18nContext';

describe('ToastContext', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows a toast when a global API error event is dispatched', async () => {
    render(
      <ToastProvider>
        <div>child</div>
      </ToastProvider>
    );

    act(() => {
      window.dispatchEvent(new CustomEvent('careeros:api-error', { detail: { message: 'Boom' } }));
    });

    expect(screen.getByText('Boom')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(5000);
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.queryByText('Boom')).not.toBeInTheDocument();
  });

  it('translates message keys at render time', () => {
    window.localStorage.setItem('careeros.interface-language', 'it');
    render(
      <I18nProvider>
        <ToastProvider><div>child</div></ToastProvider>
      </I18nProvider>
    );

    act(() => {
      window.dispatchEvent(new CustomEvent('careeros:api-error', {
        detail: { messageKey: 'searchStatus.startFailed', variables: { id: '42' } },
      }));
    });

    expect(screen.getByText('La ricerca 42 non è partita. Riprova.')).toBeInTheDocument();
  });
});
