import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { SearchProgress } from './SearchProgress';

vi.mock('../services/search', () => ({
  SearchService: {
    stopSearch: vi.fn(),
  },
}));

vi.mock('./SearchProgress/ProgressHeader', () => ({
  ProgressHeader: () => <div data-testid="progress-header" />,
}));

vi.mock('./SearchProgress/ProgressBar', () => ({
  ProgressBar: () => <div data-testid="progress-bar" />,
}));

vi.mock('./SearchProgress/TargetQueue', () => ({
  TargetQueue: () => <div data-testid="target-queue" />,
}));

vi.mock('./SearchProgress/LiveLogs', () => ({
  LiveLogs: () => <div data-testid="live-logs" />,
}));

describe('SearchProgress', () => {
  it('shows completion notice for no_results terminal reason', () => {
    const status = {
      state: 'done',
      terminal_reason: 'no_results',
      total_searches: 2,
      current_search_index: 2,
      current_query: '',
      searches_generated: [],
      jobs_new: 0,
      jobs_duplicates: 0,
      jobs_skipped: 0,
      errors: 0,
      log: [],
    };

    render(<SearchProgress profileId="1" status={status} onStateChange={vi.fn()} onClear={vi.fn()} />);

    expect(
      screen.getByText('Search completed with notice: no jobs were found for the generated queries.')
    ).toBeInTheDocument();
    expect(screen.getByTestId('llm-debug-label')).toHaveTextContent(
      'LLM_DEBUG state=done terminal_reason=no_results profile_id=1'
    );
  });

  it('shows completion notice for structured filtering terminal reason', () => {
    const status = {
      state: 'done',
      terminal_reason: 'no_jobs_after_structured_filters',
      total_searches: 3,
      current_search_index: 3,
      current_query: '',
      searches_generated: [],
      jobs_new: 0,
      jobs_duplicates: 1,
      jobs_skipped: 5,
      errors: 0,
      log: [],
    };

    render(<SearchProgress profileId="1" status={status} onStateChange={vi.fn()} onClear={vi.fn()} />);

    expect(
      screen.getByText('Search completed with notice: all fetched jobs were filtered out by structured constraints.')
    ).toBeInTheDocument();
    expect(screen.getByTestId('llm-debug-label')).toHaveTextContent(
      'LLM_DEBUG state=done terminal_reason=no_jobs_after_structured_filters profile_id=1'
    );
  });

  it('does not show completion notice for fully completed runs', () => {
    const status = {
      state: 'done',
      terminal_reason: 'completed',
      total_searches: 2,
      current_search_index: 2,
      current_query: '',
      searches_generated: [],
      jobs_new: 2,
      jobs_duplicates: 0,
      jobs_skipped: 0,
      errors: 0,
      log: [],
    };

    render(<SearchProgress profileId="1" status={status} onStateChange={vi.fn()} onClear={vi.fn()} />);

    expect(screen.queryByText(/Search completed with notice:/)).not.toBeInTheDocument();
    expect(screen.getByTestId('llm-debug-label')).toHaveTextContent(
      'LLM_DEBUG state=done terminal_reason=completed profile_id=1'
    );
  });
});
