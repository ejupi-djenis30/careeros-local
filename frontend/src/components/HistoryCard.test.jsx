import React from 'react';
import { screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { HistoryCard } from './HistoryCard';
import { renderWithI18n as render } from '../test/renderWithI18n';

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
        expect(screen.getByText(/Runs automatically every/)).toBeInTheDocument();
    });

    it('renders default location text when location is missing', () => {
        const profileWithoutLocation = { ...mockProfile, location_filter: '' };
        render(<HistoryCard profile={profileWithoutLocation} />);

        expect(screen.getByText('Any location')).toBeInTheDocument();
    });

    it('formats distances and counters with the selected interface locale', () => {
        render(
            <HistoryCard
                profile={{
                    ...mockProfile,
                    posted_within_days: 12345,
                    max_distance: 12345,
                    schedule_interval_hours: 12345,
                }}
            />,
            { language: 'it' },
        );

        expect(screen.getByText('Ultimi 12.345 giorni')).toBeInTheDocument();
        expect(screen.getByText('12.345 km')).toBeInTheDocument();
        expect(screen.getByText('Esecuzione automatica ogni 12.345 ore')).toBeInTheDocument();
    });

    it('does not display schedule info if schedule is disabled', () => {
        const profileUnscheduled = { ...mockProfile, schedule_enabled: false };
        render(<HistoryCard profile={profileUnscheduled} />);

        expect(screen.queryByText(/Runs automatically every/)).not.toBeInTheDocument();
    });

    it('calls onStartSearch when Run button is clicked', () => {
        const onStartSearch = vi.fn();
        render(<HistoryCard profile={mockProfile} onStartSearch={onStartSearch} />);

        const runButton = screen.getByTitle('Run this search again');
        fireEvent.click(runButton);

        expect(onStartSearch).toHaveBeenCalledWith(mockProfile);
    });

    it('calls rerun handlers with regeneration options', () => {
        const onStartSearchWithOptions = vi.fn();
        render(<HistoryCard profile={mockProfile} onStartSearchWithOptions={onStartSearchWithOptions} />);

        fireEvent.click(screen.getByTitle('Run again with new queries only'));
        expect(onStartSearchWithOptions).toHaveBeenCalledWith(mockProfile, { force_regenerate_queries: true });

        fireEvent.click(screen.getByTitle('Run again with a new CV summary only'));
        expect(onStartSearchWithOptions).toHaveBeenCalledWith(mockProfile, { force_regenerate_cv_summary: true });

        fireEvent.click(screen.getByTitle('Run again with a new CV summary and new queries'));
        expect(onStartSearchWithOptions).toHaveBeenCalledWith(mockProfile, {
            force_regenerate_cv_summary: true,
            force_regenerate_queries: true,
        });
    });



    it('calls onSaveAsSchedule when Add to Schedule button is clicked', () => {
        const onSaveAsSchedule = vi.fn();
        const profileUnscheduled = { ...mockProfile, schedule_enabled: false };
        render(<HistoryCard profile={profileUnscheduled} onSaveAsSchedule={onSaveAsSchedule} />);

        const scheduleButton = screen.getByTitle('Add to schedules');
        fireEvent.click(scheduleButton);
        expect(onSaveAsSchedule).toHaveBeenCalledWith(profileUnscheduled);
    });

    it('safely handles missing handlers', () => {
        render(<HistoryCard profile={mockProfile} />);
        const runButton = screen.getByTitle('Run this search again');
        fireEvent.click(runButton);

        const templateButton = screen.getByTitle('Start a new search from this one');
        fireEvent.click(templateButton);

        const profileUnscheduled = { ...mockProfile, schedule_enabled: false };
        const { getByTitle: getByTitleUnsched } = render(<HistoryCard profile={profileUnscheduled} />);

        const scheduleButton = getByTitleUnsched('Add to schedules');
        fireEvent.click(scheduleButton);
        // Should not crash
    });
});
