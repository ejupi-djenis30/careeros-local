import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ProgressHeader } from './ProgressHeader';

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

    expect(screen.getByText('Executing 2 vectors; 2 / 5 completed...')).toBeInTheDocument();
  });
});