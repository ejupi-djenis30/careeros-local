import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { HistoryCard } from './HistoryCard';

const mockProfile = {
    id: 1,
    role_description: 'Software Engineer',
    location_filter: 'Remote',
    posted_within_days: 7,
    schedule_enabled: true,
    schedule_interval_hours: 24
};

describe('HistoryCard', () => {
    it('renders profile details correctly', () => {
        render(<HistoryCard profile={mockProfile} />);

        expect(screen.getByText('Software Engineer')).toBeInTheDocument();
        expect(screen.getByText('Remote')).toBeInTheDocument();
        expect(screen.getByText('Last 7 days')).toBeInTheDocument();
        expect(screen.getByText(/Auto every/)).toBeInTheDocument();
    });

    it('renders default location text when location is missing', () => {
        const profileWithoutLocation = { ...mockProfile, location_filter: '' };
        render(<HistoryCard profile={profileWithoutLocation} />);

        expect(screen.getByText('Any Location')).toBeInTheDocument();
    });

    it('does not display schedule info if schedule is disabled', () => {
        const profileUnscheduled = { ...mockProfile, schedule_enabled: false };
        render(<HistoryCard profile={profileUnscheduled} />);

        expect(screen.queryByText(/Auto-runs every/)).not.toBeInTheDocument();
    });

    it('calls onStartSearch when Run button is clicked', () => {
        const onStartSearch = vi.fn();
        render(<HistoryCard profile={mockProfile} onStartSearch={onStartSearch} />);

        const runButton = screen.getByTitle('Rerun Search');
        fireEvent.click(runButton);

        expect(onStartSearch).toHaveBeenCalledWith(mockProfile);
    });

    it('calls rerun handlers with regeneration options', () => {
        const onStartSearchWithOptions = vi.fn();
        render(<HistoryCard profile={mockProfile} onStartSearchWithOptions={onStartSearchWithOptions} />);

        fireEvent.click(screen.getByTitle('Rerun with fresh queries only'));
        expect(onStartSearchWithOptions).toHaveBeenCalledWith(mockProfile, { force_regenerate_queries: true });

        fireEvent.click(screen.getByTitle('Rerun with fresh CV summary only'));
        expect(onStartSearchWithOptions).toHaveBeenCalledWith(mockProfile, { force_regenerate_cv_summary: true });

        fireEvent.click(screen.getByTitle('Rerun with fresh CV summary and queries (full refresh)'));
        expect(onStartSearchWithOptions).toHaveBeenCalledWith(mockProfile, {
            force_regenerate_cv_summary: true,
            force_regenerate_queries: true,
        });
    });



    it('calls onSaveAsSchedule when Add to Schedule button is clicked', () => {
        const onSaveAsSchedule = vi.fn();
        const profileUnscheduled = { ...mockProfile, schedule_enabled: false };
        render(<HistoryCard profile={profileUnscheduled} onSaveAsSchedule={onSaveAsSchedule} />);

        const scheduleButton = screen.getByTitle('Add to Schedule');
        fireEvent.click(scheduleButton);
        expect(onSaveAsSchedule).toHaveBeenCalledWith(profileUnscheduled);
    });

    it('safely handles missing handlers', () => {
        render(<HistoryCard profile={mockProfile} />);
        const runButton = screen.getByTitle('Rerun Search');
        fireEvent.click(runButton);

        const templateButton = screen.getByTitle('New Search from this');
        fireEvent.click(templateButton);

        const profileUnscheduled = { ...mockProfile, schedule_enabled: false };
        const { getByTitle: getByTitleUnsched } = render(<HistoryCard profile={profileUnscheduled} />);

        const scheduleButton = getByTitleUnsched('Add to Schedule');
        fireEvent.click(scheduleButton);
        // Should not crash
    });
});
