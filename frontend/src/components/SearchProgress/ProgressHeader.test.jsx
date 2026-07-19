import React from 'react';
import { screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ProgressHeader } from './ProgressHeader';
import { renderWithI18n as render } from '../../test/renderWithI18n';

describe('ProgressHeader', () => {
  it('describes concurrent search progress using active and completed counts', () => {
    render(
      <ProgressHeader
        isDone={false}
        isError={false}
        isRunning
        state="searching"
        searches_completed={2}
        active_search_indices={[3, 4]}
        total_searches={5}
        handleStop={vi.fn()}
        onClear={vi.fn()}
      />
    );

    expect(screen.getByText('Running 2 queries; 2 of 5 completed…')).toBeInTheDocument();
  });

  it('formats search counters with the selected interface locale', () => {
    render(
      <ProgressHeader
        isDone={false}
        isError={false}
        isRunning
        state="searching"
        searches_completed={12345}
        active_search_indices={[12346]}
        total_searches={50000}
        handleStop={vi.fn()}
        onClear={vi.fn()}
      />,
      { language: 'it' },
    );

    expect(screen.getByText('Esecuzione di 1 query; 12.345 su 50.000 completate…')).toBeInTheDocument();
  });
});
