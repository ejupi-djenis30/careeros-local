import React from 'react';
import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ToastProvider } from './ToastContext';

describe('ToastContext', () => {
  beforeEach(() => {
    vi.useFakeTimers();
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
});
