import React, { createRef } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
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
});