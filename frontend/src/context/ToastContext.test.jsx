import React from 'react';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ToastProvider, useToast } from './ToastContext';
import { I18nProvider } from '../i18n/I18nContext';
import { LanguageSwitcher } from '../i18n/LanguageSwitcher';

function ActionToastHarness() {
  const { showToast } = useToast();
  return (
    <button
      type="button"
      onClick={() => showToast(
        { messageKey: 'jobs.dismissed' },
        'secondary',
        { labelKey: 'jobs.undo', onAction: vi.fn() },
      )}
    >
      Show toast
    </button>
  );
}

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

  it('retranslates a visible message without cancelling its original timeout', async () => {
    window.localStorage.setItem('careeros.interface-language', 'it');
    render(
      <I18nProvider>
        <ToastProvider><LanguageSwitcher /></ToastProvider>
      </I18nProvider>
    );

    act(() => {
      window.dispatchEvent(new CustomEvent('careeros:api-error', {
        detail: { messageKey: 'searchStatus.startFailed', variables: { id: '42' } },
      }));
    });

    expect(screen.getByText('La ricerca 42 non è partita. Riprova.')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    fireEvent.click(screen.getByRole('button', { name: 'Inglese' }));
    expect(screen.getByText('Search 42 did not start. Please try again.')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(2999);
    });
    expect(screen.getByText('Search 42 did not start. Please try again.')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1);
    });
    await act(async () => Promise.resolve());
    expect(screen.queryByText('Search 42 did not start. Please try again.')).not.toBeInTheDocument();
  });

  it('retranslates action labels stored as semantic keys', () => {
    render(
      <I18nProvider>
        <ToastProvider>
          <LanguageSwitcher />
          <ActionToastHarness />
        </ToastProvider>
      </I18nProvider>
    );

    fireEvent.click(screen.getByRole('button', { name: 'Show toast' }));
    expect(screen.getByRole('button', { name: 'Undo' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Italian' }));
    expect(screen.getByRole('button', { name: 'Annulla' })).toBeInTheDocument();
  });
});
