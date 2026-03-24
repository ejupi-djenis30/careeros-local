import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ScoreBadge, DistanceBadge } from './Badges';

describe('ScoreBadge', () => {
    it('renders successfully for high scores', () => {
        render(<ScoreBadge score={90} />);
        const badge = screen.getByText('90%');
        expect(badge).toBeInTheDocument();
        expect(badge).toHaveClass('badge-success');
        expect(badge.querySelector('.bi-check-lg')).toBeInTheDocument();
    });

    it('renders warning styles for medium scores', () => {
        render(<ScoreBadge score={75} />);
        const badge = screen.getByText('75%');
        expect(badge).toBeInTheDocument();
        expect(badge).toHaveClass('badge-warning');
        expect(badge.querySelector('.bi-exclamation')).toBeInTheDocument();
    });

    it('renders secondary styles for low scores', () => {
        render(<ScoreBadge score={60} />);
        const badge = screen.getByText('60%');
        expect(badge).toBeInTheDocument();
        expect(badge).toHaveClass('badge-secondary');
        expect(badge.querySelector('.bi-dash')).toBeInTheDocument();
    });
});

describe('DistanceBadge', () => {
    it('renders with valid distance', () => {
        render(<DistanceBadge km={15} />);
        expect(screen.getByText('15km')).toBeInTheDocument();
        const icon = document.querySelector('.bi-geo-alt');
        expect(icon).toBeInTheDocument();
    });

    it('renders em-dash for undefined distance', () => {
        render(<DistanceBadge km={null} />);
        expect(screen.getByText('—')).toBeInTheDocument();
    });

    it('renders text-success for distance <= 15', () => {
        render(<DistanceBadge km={10} />);
        const badge = screen.getByText('10km').closest('span');
        expect(badge).toHaveClass('text-success');
    });

    it('renders text-info for distance between 15 and 40', () => {
        render(<DistanceBadge km={25} />);
        const badge = screen.getByText('25km').closest('span');
        expect(badge).toHaveClass('text-info');
    });

    it('renders text-secondary for distance > 40', () => {
        render(<DistanceBadge km={50} />);
        const badge = screen.getByText('50km').closest('span');
        expect(badge).toHaveClass('text-secondary');
    });
});
