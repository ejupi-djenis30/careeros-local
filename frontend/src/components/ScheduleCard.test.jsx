import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ScheduleCard } from './ScheduleCard';

const mockProfile = {
    id: 10,
    name: 'Custom Campaign Name',
    role_description: 'Frontend Developer',
    location_filter: 'Berlin',
    schedule_enabled: true,
    schedule_interval_hours: 12
};

describe('ScheduleCard', () => {
    it('renders profile details and custom name correctly', () => {
        render(<ScheduleCard profile={mockProfile} onToggle={vi.fn()} onChangeInterval={vi.fn()} onDelete={vi.fn()} />);

        expect(screen.getByText('Custom Campaign Name')).toBeInTheDocument();
        expect(screen.getByText('Frontend Developer')).toBeInTheDocument();
        expect(screen.getByText('Berlin')).toBeInTheDocument();
        expect(screen.getByText('ID: 10')).toBeInTheDocument();
    });

    it('renders default name and falsy fallbacks when profile is missing info', () => {
        const profileMissingInfo = { ...mockProfile, name: '', location_filter: '', schedule_interval_hours: null };
        render(<ScheduleCard profile={profileMissingInfo} onToggle={vi.fn()} onChangeInterval={vi.fn()} onDelete={vi.fn()} />);

        expect(screen.getByText('Campaign #10')).toBeInTheDocument();
        expect(screen.getByText('Any Location')).toBeInTheDocument();
        const select = screen.getByRole('combobox');
        expect(select.value).toBe("24"); // Checks the fallback
    });

    it('calls onToggle when schedule switch is clicked', () => {
        const onToggle = vi.fn();
        render(<ScheduleCard profile={mockProfile} onToggle={onToggle} onChangeInterval={vi.fn()} onDelete={vi.fn()} />);

        const toggleSwitch = screen.getByRole('checkbox');
        // Initial state
        expect(toggleSwitch).toBeChecked();

        fireEvent.click(toggleSwitch);

        // Ensure the handler was called with the correct previous state
        expect(onToggle).toHaveBeenCalledWith(mockProfile.id, true, 12);
    });

    it('calls onChangeInterval when select value changes', () => {
        const onChangeInterval = vi.fn();
        render(<ScheduleCard profile={mockProfile} onToggle={vi.fn()} onChangeInterval={onChangeInterval} onDelete={vi.fn()} />);

        const select = screen.getByRole('combobox');
        expect(select.value).toBe('12');

        fireEvent.change(select, { target: { value: '24' } });

        expect(onChangeInterval).toHaveBeenCalledWith(mockProfile.id, '24');
    });

    it('calls onDelete when delete button is clicked', () => {
        const onDelete = vi.fn();
        render(<ScheduleCard profile={mockProfile} onToggle={vi.fn()} onChangeInterval={vi.fn()} onDelete={onDelete} />);

        const deleteBtn = screen.getByTitle('Delete Campaign');
        fireEvent.click(deleteBtn);

        expect(onDelete).toHaveBeenCalledWith(mockProfile.id);
    });

    it('handles disabled schedule state', () => {
        const disabledProfile = { ...mockProfile, schedule_enabled: false };
        render(<ScheduleCard profile={disabledProfile} onToggle={vi.fn()} onChangeInterval={vi.fn()} onDelete={vi.fn()} />);
        const toggleSwitch = screen.getByRole('checkbox');
        expect(toggleSwitch).not.toBeChecked();
    });
});
