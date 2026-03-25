import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { LiveLogs } from './LiveLogs';

describe('LiveLogs', () => {
  it('renders LLM_DEBUG logs as structured key/value badges', () => {
    const log = [
      {
        time: '2026-03-25T01:14:05.000Z',
        message: '[LLM_DEBUG] state=done terminal_reason=no_queries profile_id=1',
      },
    ];

    render(<LiveLogs log={log} logEndRef={{ current: null }} />);

    expect(screen.getByTestId('llm-debug-log-row')).toBeInTheDocument();
    expect(screen.getByText('LLM_DEBUG')).toBeInTheDocument();
    expect(screen.getByText('state:done')).toBeInTheDocument();
    expect(screen.getByText('terminal_reason:no_queries')).toBeInTheDocument();
    expect(screen.getByText('profile_id:1')).toBeInTheDocument();
  });

  it('keeps non-debug logs unchanged', () => {
    const log = [
      {
        time: '2026-03-25T01:14:05.000Z',
        message: 'Step 1: Generating/Retrieving search plan...',
      },
    ];

    render(<LiveLogs log={log} logEndRef={{ current: null }} />);

    expect(screen.queryByTestId('llm-debug-log-row')).not.toBeInTheDocument();
    expect(screen.getByText('Step 1: Generating/Retrieving search plan...')).toBeInTheDocument();
  });
});
