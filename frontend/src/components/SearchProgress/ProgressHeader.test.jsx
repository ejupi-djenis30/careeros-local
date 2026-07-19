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
});
