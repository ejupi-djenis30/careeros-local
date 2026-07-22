import React from 'react';
import { screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { SearchProgress } from './SearchProgress';
import { ToastProvider } from '../context/ToastContext';
import { renderWithI18n as render } from '../test/renderWithI18n';

vi.mock('../services/search', () => ({
  SearchService: {
    stopSearch: vi.fn(),
  },
}));

vi.mock('./SearchProgress/ProgressHeader', () => ({
  ProgressHeader: (props) => (
    <div
      data-testid="progress-header"
      data-searches-completed={props.searches_completed ?? ''}
      data-active-count={props.active_search_indices?.length ?? 0}
    />
  ),
}));

vi.mock('./SearchProgress/ProgressBar', () => ({
  ProgressBar: (props) => <div data-testid="progress-bar" data-progress-pct={props.progressPct} />,
}));

vi.mock('./SearchProgress/TargetQueue', () => ({
  TargetQueue: (props) => (
    <div
      data-testid="target-queue"
      data-active-indices={(props.active_search_indices || []).join(',')}
      data-completed-indices={(props.completed_search_indices || []).join(',')}
      data-analyzed-count={props.analyzedJobs?.length ?? 0}
    />
  ),
}));

vi.mock('./SearchProgress/LiveLogs', () => ({
  LiveLogs: () => <div data-testid="live-logs" />,
}));

describe('SearchProgress', () => {
  it('reports a user-stopped search as a terminal state', async () => {
    const onStateChange = vi.fn();
    const status = {
      state: 'stopped',
      total_searches: 1,
      searches_generated: [],
      active_search_indices: [],
      completed_search_indices: [],
      jobs_new: 0,
      jobs_unique: 0,
      jobs_skipped: 0,
      errors: 0,
      log: [],
    };

    render(<ToastProvider><SearchProgress profileId="1" status={status} onStateChange={onStateChange} onClear={vi.fn()} /></ToastProvider>);
    await waitFor(() => expect(onStateChange).toHaveBeenCalledWith('stopped'));
  });

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

    render(<ToastProvider><SearchProgress profileId="1" status={status} onStateChange={vi.fn()} onClear={vi.fn()} /></ToastProvider>);

    expect(
      screen.getByText('The generated queries did not return any jobs.')
    ).toBeInTheDocument();
    expect(screen.getByTestId('llm-debug-label')).toHaveTextContent(
      'LLM_DEBUG state=done terminal_reason=no_results profile_id=1'
    );
  });

  it('explains the deterministic explicit-query requirement from the backend reason', () => {
    const status = {
      state: 'done',
      terminal_reason: 'no_explicit_queries',
      total_searches: 0,
      searches_generated: [],
      jobs_new: 0,
      jobs_duplicates: 0,
      jobs_skipped: 0,
      errors: 0,
      log: [],
    };

    render(<ToastProvider><SearchProgress profileId="1" status={status} onStateChange={vi.fn()} onClear={vi.fn()} /></ToastProvider>);

    expect(screen.getByText('Add at least one role or keyword to start a provider search.')).toBeInTheDocument();
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

    render(<ToastProvider><SearchProgress profileId="1" status={status} onStateChange={vi.fn()} onClear={vi.fn()} /></ToastProvider>);

    expect(
      screen.getByText('Every fetched job was excluded by the structured filters.')
    ).toBeInTheDocument();
    expect(screen.getByTestId('llm-debug-label')).toHaveTextContent(
      'LLM_DEBUG state=done terminal_reason=no_jobs_after_structured_filters profile_id=1'
    );
  });

  it('shows completion notice for no_jobs_after_dedup terminal reason', () => {
    const status = {
      state: 'done',
      terminal_reason: 'no_jobs_after_dedup',
      total_searches: 2,
      current_search_index: 2,
      current_query: '',
      searches_generated: [],
      jobs_new: 0,
      jobs_duplicates: 4,
      jobs_skipped: 0,
      errors: 0,
      log: [],
    };

    render(<ToastProvider><SearchProgress profileId="1" status={status} onStateChange={vi.fn()} onClear={vi.fn()} /></ToastProvider>);

    expect(
      screen.getByText('No jobs remained after removing duplicates from this run.')
    ).toBeInTheDocument();
    expect(screen.getByTestId('llm-debug-label')).toHaveTextContent(
      'LLM_DEBUG state=done terminal_reason=no_jobs_after_dedup profile_id=1'
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

    render(<ToastProvider><SearchProgress profileId="1" status={status} onStateChange={vi.fn()} onClear={vi.fn()} /></ToastProvider>);

    expect(screen.queryByText(/Search completed with notice:/)).not.toBeInTheDocument();
    expect(screen.getByTestId('llm-debug-label')).toHaveTextContent(
      'LLM_DEBUG state=done terminal_reason=completed profile_id=1'
    );
  });

  it('shows error notice for pipeline processing failures', () => {
    const status = {
      state: 'error',
      terminal_reason: 'pipeline_processing_failed',
      total_searches: 3,
      current_search_index: 3,
      current_query: '',
      searches_generated: [],
      jobs_new: 0,
      jobs_duplicates: 0,
      jobs_skipped: 2,
      errors: 1,
      log: [],
    };

    render(<ToastProvider><SearchProgress profileId="1" status={status} onStateChange={vi.fn()} onClear={vi.fn()} /></ToastProvider>);

    expect(
      screen.getByText('The search failed while processing jobs, before analysis finished.')
    ).toBeInTheDocument();
    expect(screen.getByTestId('llm-debug-label')).toHaveTextContent(
      'LLM_DEBUG state=error terminal_reason=pipeline_processing_failed profile_id=1'
    );
  });

  it('renders duplicate breakdown when provided by backend status', () => {
    const status = {
      state: 'searching',
      terminal_reason: null,
      total_searches: 2,
      current_search_index: 1,
      current_query: 'backend engineer',
      searches_generated: [],
      jobs_new: 0,
      jobs_unique: 1,
      jobs_duplicates: 3,
      jobs_duplicates_total: 3,
      jobs_duplicates_runtime: 1,
      jobs_duplicates_history: 2,
      jobs_duplicates_catalog_conflicts: 4,
      jobs_skipped: 0,
      errors: 0,
      log: [],
    };

    render(<ToastProvider><SearchProgress profileId="1" status={status} onStateChange={vi.fn()} onClear={vi.fn()} /></ToastProvider>);

    expect(screen.getByText('R 1 H 2 C 4')).toBeInTheDocument();
  });

  it('uses completed query counts instead of current index for concurrent progress', () => {
    const status = {
      state: 'searching',
      terminal_reason: null,
      total_searches: 4,
      current_search_index: 3,
      searches_completed: 1,
      active_search_indices: [2, 3],
      completed_search_indices: [1],
      current_query: 'data engineer',
      searches_generated: [{ query: 'a' }, { query: 'b' }, { query: 'c' }, { query: 'd' }],
      jobs_new: 0,
      jobs_duplicates: 0,
      jobs_skipped: 0,
      jobs_analyzed: 0,
      jobs_analyze_total: 0,
      errors: 0,
      log: [],
    };

    render(<ToastProvider><SearchProgress profileId="1" status={status} onStateChange={vi.fn()} onClear={vi.fn()} /></ToastProvider>);

    expect(screen.getByTestId('progress-bar')).toHaveAttribute('data-progress-pct', '26');
    expect(screen.getByTestId('progress-header')).toHaveAttribute('data-searches-completed', '1');
    expect(screen.getByTestId('progress-header')).toHaveAttribute('data-active-count', '2');
    expect(screen.getByTestId('target-queue')).toHaveAttribute('data-active-indices', '2,3');
    expect(screen.getByTestId('target-queue')).toHaveAttribute('data-completed-indices', '1');
  });

  it('does not spike to 90% when first analysis batch equals total (jobs_analyzed == jobs_analyze_total)', () => {
    // Regression: when the first batch completes and jobs_analyzed === jobs_analyze_total
    // the old code produced analysisPct = 90 % (ratio 1.0).  The fix requires
    // analysisRunning = false when the ratio is 1.0, so searchPct dominates.
    const status = {
      state: 'searching',
      terminal_reason: null,
      total_searches: 4,
      searches_completed: 1,
      active_search_indices: [2],
      completed_search_indices: [1],
      current_query: 'dev',
      searches_generated: [{ query: 'a' }, { query: 'b' }, { query: 'c' }, { query: 'd' }],
      jobs_new: 0,
      jobs_duplicates: 0,
      jobs_skipped: 0,
      // First batch complete: analyzed == total → analysisRunning must be false
      jobs_analyzed: 10,
      jobs_analyze_total: 10,
      errors: 0,
      log: [],
    };

    render(<ToastProvider><SearchProgress profileId="1" status={status} onStateChange={vi.fn()} onClear={vi.fn()} /></ToastProvider>);

    const pct = parseInt(screen.getByTestId('progress-bar').getAttribute('data-progress-pct'), 10);
    // searchPct = 5 + (1/4)*85 = 26. Must be ≤ 30, never 90.
    expect(pct).toBeLessThanOrEqual(30);
    expect(pct).toBeGreaterThanOrEqual(5);
  });

  it('shows analysis progress when more jobs are queued than analyzed (stable ratio)', () => {
    // When jobs_analyze_total > jobs_analyzed, analysisRunning should be true
    // and analysisPct should dominate if it is higher than searchPct.
    const status = {
      state: 'searching',
      terminal_reason: null,
      total_searches: 4,
      searches_completed: 1,
      active_search_indices: [2],
      completed_search_indices: [1],
      current_query: 'dev',
      searches_generated: [{ query: 'a' }, { query: 'b' }, { query: 'c' }, { query: 'd' }],
      jobs_new: 0,
      jobs_duplicates: 0,
      jobs_skipped: 0,
      // 30 analyzed out of 50 expected → ratio 0.6 → analysisPct = 5 + 0.6*85 ≈ 56
      jobs_analyzed: 30,
      jobs_analyze_total: 50,
      errors: 0,
      log: [],
    };

    render(<ToastProvider><SearchProgress profileId="1" status={status} onStateChange={vi.fn()} onClear={vi.fn()} /></ToastProvider>);

    const pct = parseInt(screen.getByTestId('progress-bar').getAttribute('data-progress-pct'), 10);
    // analysisPct ≈ 56, searchPct = 26. Bar should reflect analysis progress.
    expect(pct).toBeGreaterThanOrEqual(50);
    expect(pct).toBeLessThanOrEqual(65);
  });

  it('builds the refinement queue from structured analysis targets instead of log parsing', () => {
    const status = {
      state: 'analyzing',
      terminal_reason: null,
      total_searches: 1,
      current_search_index: 1,
      current_query: 'backend engineer',
      searches_generated: [{ query: 'backend engineer' }],
      jobs_new: 0,
      jobs_duplicates: 0,
      jobs_skipped: 0,
      jobs_analyzed: 1,
      jobs_analyze_total: 3,
      analysis_current_index: 2,
      analysis_targets: [
        { title: 'Backend Engineer' },
        { title: 'Platform Engineer' },
        { title: 'Data Engineer' },
      ],
      errors: 0,
      log: [{ message: 'legacy log that should be ignored' }],
    };

    render(<ToastProvider><SearchProgress profileId="1" status={status} onStateChange={vi.fn()} onClear={vi.fn()} /></ToastProvider>);

    expect(screen.getByTestId('target-queue')).toHaveAttribute('data-analyzed-count', '3');
  });
});
