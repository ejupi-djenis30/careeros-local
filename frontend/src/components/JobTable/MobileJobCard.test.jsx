import React from 'react';
import { screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MobileJobCard } from './MobileJobCard';
import { renderWithI18n as render } from '../../test/renderWithI18n';

describe('MobileJobCard', () => {
    const mockJob = {
        id: 1,
        title: 'Software Engineer',
        company: 'Tech Corp',
        location: 'Zürich',
        distance_km: 10,
        affinity_score: 85,
        worth_applying: true,
        workload: 100,
        applied: false,
        created_at: '2024-02-21T10:00:00Z',
        application_url: 'http://apply.com',
        external_url: 'http://source.com',
        application_email: 'jobs@techcorp.example.test',
        affinity_analysis: 'Analysis text',
        analysis_verified: true
    };

    const mockHandlers = {
        onCopy: vi.fn()
    };

    it('renders basic job info', () => {
        render(<MobileJobCard job={mockJob} {...mockHandlers} />);
        expect(screen.getByText('Software Engineer')).toBeInTheDocument();
        expect(screen.getByText('Tech Corp')).toBeInTheDocument();
        expect(screen.getByText('Zürich')).toBeInTheDocument();
        expect(screen.getByText('10 km')).toBeInTheDocument();
        expect(screen.getByText('100%')).toBeInTheDocument();
    });

    it('renders publication date if present in job payload', () => {
        const publishedJob = { ...mockJob, publication_date: '2024-03-01T12:00:00Z' };
        render(<MobileJobCard job={publishedJob} {...mockHandlers} />);
        expect(screen.getByText(new Date('2024-03-01T12:00:00Z').toLocaleDateString('en-GB'))).toBeInTheDocument();
    });

    it('renders ScoreBadge when not in global view', () => {
        render(<MobileJobCard job={mockJob} isGlobalView={false} {...mockHandlers} />);
        expect(screen.getByText('85%')).toBeInTheDocument();
    });

    it('does not render ScoreBadge in global view', () => {
        render(<MobileJobCard job={mockJob} isGlobalView={true} {...mockHandlers} />);
        expect(screen.queryByText('85%')).not.toBeInTheDocument();
    });

    it('renders Top Pick badge when worth applying', () => {
        render(<MobileJobCard job={mockJob} isGlobalView={false} {...mockHandlers} />);
        expect(screen.getByTitle('Top pick')).toBeInTheDocument();
    });

    it('offers one route to track an untracked job', () => {
        render(<MobileJobCard job={mockJob} {...mockHandlers} />);
        expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
        expect(screen.getByText('Not tracked')).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Track application' })).toHaveAttribute('href', '/applications?jobId=1');
    });

    it('opens an existing application and shows its stage', () => {
        const trackedJob = {
            ...mockJob,
            application_id: '44444444-4444-4444-8444-444444444444',
            application_stage: 'interview',
        };
        render(<MobileJobCard job={trackedJob} {...mockHandlers} />);

        expect(screen.getByText('Interview')).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Open application' })).toHaveAttribute(
            'href',
            '/applications?applicationId=44444444-4444-4444-8444-444444444444',
        );
    });

    it('keeps the legacy applied flag explicit without treating it as a pipeline record', () => {
        render(<MobileJobCard job={{ ...mockJob, applied: true }} {...mockHandlers} />);

        expect(screen.getByText('Applied · legacy')).toBeInTheDocument();
        expect(screen.getByText(/Create a full application record/)).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Track application' })).toBeInTheDocument();
    });

    it('calls onCopy when copy button clicked', () => {
        render(<MobileJobCard job={mockJob} {...mockHandlers} />);
        const copyBtn = screen.getByTitle('Copy job information');
        fireEvent.click(copyBtn);
        expect(mockHandlers.onCopy).toHaveBeenCalledWith(mockJob);
    });

    it('renders the external application page as a secondary action', () => {
        render(<MobileJobCard job={mockJob} {...mockHandlers} />);
        const applyLink = screen.getByTitle('Open application page');
        expect(applyLink).toHaveAttribute('href', mockJob.application_url);
    });

    it('uses external_url if application_url is missing', () => {
        const jobNoApply = { ...mockJob, application_url: null };
        render(<MobileJobCard job={jobNoApply} {...mockHandlers} />);
        const applyLink = screen.getByTitle('Open application page');
        expect(applyLink).toHaveAttribute('href', mockJob.external_url);
    });

    it('renders email link when application_email is present', () => {
        render(<MobileJobCard job={mockJob} {...mockHandlers} />);
        const emailLink = screen.getByTitle('Email');
        expect(emailLink).toHaveAttribute('href', `mailto:${mockJob.application_email}`);
    });

    it('calls onViewAnalysis when analysis button clicked', () => {
        const onViewAnalysis = vi.fn();
        render(<MobileJobCard job={mockJob} onViewAnalysis={onViewAnalysis} {...mockHandlers} />);
        const analysisBtn = screen.getByTitle('View match analysis');
        fireEvent.click(analysisBtn);
        expect(onViewAnalysis).toHaveBeenCalledWith(mockJob);
    });

    it('hides every analysis-derived field when the result is not verified', () => {
        const unverifiedJob = { ...mockJob, analysis_verified: false };
        render(<MobileJobCard job={unverifiedJob} isGlobalView={false} {...mockHandlers} />);

        expect(screen.queryByText('85%')).not.toBeInTheDocument();
        expect(screen.queryByTitle('Top pick')).not.toBeInTheDocument();
        expect(screen.queryByTitle('View match analysis')).not.toBeInTheDocument();
    });
});
