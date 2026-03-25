import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { FilterBar } from './FilterBar';

describe('FilterBar', () => {
  it('renders safely with missing filters and invalid profile input', () => {
    render(<FilterBar onChange={vi.fn()} onClear={vi.fn()} searchProfiles={null} />);

    expect(screen.getByDisplayValue('Global Dashboard')).toBeInTheDocument();
  });

  it('emits a sort change using default filter state', () => {
    const onChange = vi.fn();
    render(<FilterBar onChange={onChange} onClear={vi.fn()} searchProfiles={[]} />);

    const selects = screen.getAllByRole('combobox');

    fireEvent.change(selects[1], {
      target: { value: 'created_at:asc' }
    });

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ sort_by: 'created_at', sort_order: 'asc' }));
  });

  it('does not render deprecated tech-domain badges for scoped profiles', () => {
    render(
      <FilterBar
        filters={{ search_profile_id: 7 }}
        onChange={vi.fn()}
        onClear={vi.fn()}
        searchProfiles={[
          {
            id: 7,
            preferred_languages: ['de'],
            preferred_domains: ['backend'],
            remote_only: true,
          }
        ]}
      />
    );

    expect(screen.getByText('DE')).toBeInTheDocument();
    expect(screen.getByText('Remote')).toBeInTheDocument();
    expect(screen.queryByText('backend')).not.toBeInTheDocument();
  });
});