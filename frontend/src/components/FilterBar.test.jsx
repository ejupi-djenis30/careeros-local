import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { FilterBar } from './FilterBar';
import { I18nProvider } from '../i18n/I18nContext';

function renderFilterBar(props, language = 'en') {
  window.localStorage.setItem('careeros.interface-language', language);
  return render(<I18nProvider><FilterBar {...props} /></I18nProvider>);
}

describe('FilterBar', () => {
  beforeEach(() => window.localStorage.clear());

  it('renders safely with missing filters and invalid profile input', () => {
    renderFilterBar({ onChange: vi.fn(), onClear: vi.fn(), searchProfiles: null });

    expect(screen.getByDisplayValue('All jobs')).toBeInTheDocument();
  });

  it('emits a sort change using default filter state', () => {
    const onChange = vi.fn();
    renderFilterBar({ onChange, onClear: vi.fn(), searchProfiles: [] });

    const selects = screen.getAllByRole('combobox');

    fireEvent.change(selects[1], {
      target: { value: 'created_at:asc' }
    });

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ sort_by: 'created_at', sort_order: 'asc' }));
  });

  it('does not render deprecated tech-domain badges for scoped profiles', () => {
    renderFilterBar({
        filters: { search_profile_id: 7 },
        onChange: vi.fn(),
        onClear: vi.fn(),
        searchProfiles: [
          {
            id: 7,
            preferred_languages: ['de'],
            preferred_domains: ['backend'],
            remote_only: true,
          },
        ],
      });

    expect(screen.getByText('DE')).toBeInTheDocument();
    expect(screen.getByText('Remote')).toBeInTheDocument();
    expect(screen.queryByText('backend')).not.toBeInTheDocument();
  });

  it('renders the same controls in Italian when the saved language changes', () => {
    renderFilterBar({ onChange: vi.fn(), onClear: vi.fn(), searchProfiles: [] }, 'it');

    expect(screen.getByDisplayValue('Tutti gli annunci')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Più recenti')).toBeInTheDocument();
  });
});
