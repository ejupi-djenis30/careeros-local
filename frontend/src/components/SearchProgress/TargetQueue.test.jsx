import React, { createRef } from 'react';
import { screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { renderWithI18n as render } from '../../test/renderWithI18n';
import { TargetQueue } from './TargetQueue';

describe('TargetQueue', () => {
  it('renders completed and active queries from explicit status indices', () => {
    render(
      <TargetQueue
        state="searching"
        analyzedJobs={[]}
        searches_generated={[
          { query: 'python engineer', type: 'occupation' },
          { query: 'data engineer', type: 'occupation' },
          { query: 'ml engineer', type: 'occupation' },
        ]}
        active_search_indices={[2]}
        completed_search_indices={[1]}
        activeItemRef={createRef()}
        jobs_analyzed={0}
        jobs_analyze_total={0}
      />
    );

    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(items[0].querySelector('.bi-check-circle-fill')).not.toBeNull();
    expect(items[1].querySelector('.spinner-border')).not.toBeNull();
    expect(items[2].querySelector('.bi-check-circle-fill')).toBeNull();
    expect(items[2].querySelector('.spinner-border')).toBeNull();
  });

  it('renders structured refinement queue with done current and pending states', () => {
    render(
      <TargetQueue
        state="analyzing"
        analyzedJobs={[
          { idx: 1, total: 3, title: 'Backend Engineer', status: 'done' },
          { idx: 2, total: 3, title: 'Platform Engineer', status: 'analyzing' },
          { idx: 3, total: 3, title: 'Data Engineer', status: 'pending' },
        ]}
        searches_generated={[]}
        active_search_indices={[]}
        completed_search_indices={[]}
        activeItemRef={createRef()}
        jobs_analyzed={1}
        jobs_analyze_total={3}
      />
    );

    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(items[0].querySelector('.bi-check-circle-fill')).not.toBeNull();
    expect(items[1].querySelector('.spinner-border')).not.toBeNull();
    expect(items[2].querySelector('.spinner-border')).toBeNull();
  });

  it('formats analysis counters with the selected interface locale', () => {
    render(
      <TargetQueue
        state="searching"
        analyzedJobs={[]}
        searches_generated={[]}
        active_search_indices={[]}
        completed_search_indices={[]}
        activeItemRef={createRef()}
        jobs_analyzed={12345}
        jobs_analyze_total={56789}
      />,
      { language: 'it' },
    );

    expect(screen.getByText('12.345/56.789 analizzati')).toBeInTheDocument();
  });
});
