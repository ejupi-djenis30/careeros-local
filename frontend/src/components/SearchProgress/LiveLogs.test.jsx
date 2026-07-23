import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { LiveLogs } from './LiveLogs';

describe('LiveLogs', () => {
  it('removes internal LLM debug records from the release log', () => {
    const log = [
      {
        time: '2026-03-25T01:14:05.000Z',
        message: '[LLM_DEBUG] state=done terminal_reason=no_queries profile_id=1',
      },
    ];

    render(<LiveLogs log={log} logEndRef={{ current: null }} />);

    expect(screen.queryByText(/LLM_DEBUG|profile_id|terminal_reason/)).not.toBeInTheDocument();
    expect(screen.getByText('Waiting for activity…')).toBeInTheDocument();
  });

  it('keeps non-debug logs unchanged', () => {
    const log = [
      {
        time: '2026-03-25T01:14:05.000Z',
        message: 'Step 1: Generating/Retrieving search plan...',
      },
    ];

    render(<LiveLogs log={log} logEndRef={{ current: null }} />);

    expect(screen.getByText('Step 1: Generating/Retrieving search plan...')).toBeInTheDocument();
  });

  it('redacts profile identifiers from ordinary release logs', () => {
    const log = [{
      time: '2026-03-25T01:14:05.000Z',
      message: 'Search resumed profile_id=private-42 safely',
    }];

    render(<LiveLogs log={log} logEndRef={{ current: null }} />);

    expect(screen.getByText('Search resumed safely')).toBeInTheDocument();
    expect(screen.queryByText(/private-42|profile_id/)).not.toBeInTheDocument();
  });
});
