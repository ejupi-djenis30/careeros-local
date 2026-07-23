import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { DesktopJobRow } from './DesktopJobRow';
import { renderWithI18n as render } from '../../test/renderWithI18n';

// Mock clipboard
const mockWriteText = vi.fn();
Object.assign(navigator, {
    clipboard: {
        writeText: mockWriteText,
    },
});

describe('DesktopJobRow', () => {
    const mockJob = {
        id: '1',
        title: 'Senior Developer',
        company: 'Tech Corp',
        location: 'Zürich',
        created_at: new Date().toISOString(),
        external_url: 'https://example.com/job',
        application_email: 'jobs@techcorp.example.test',
        affinity_score: 85,
        affinity_analysis: 'Great match for your Python skills.',
        analysis_verified: true,
        applied: false
    };

    const defaultProps = {
        job: mockJob,
        isGlobalView: false,
        onToggleApplied: vi.fn(),
        onCopy: vi.fn()
    };

    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('renders basic job information', () => {
        render(
            <table>
                <tbody>
                    <DesktopJobRow {...defaultProps} />
                </tbody>
            </table>
        );
        expect(screen.getByText('Senior Developer')).toBeInTheDocument();
        expect(screen.getByText('Tech Corp')).toBeInTheDocument();
        expect(screen.getByText(/Zürich/)).toBeInTheDocument();
    });

    it('shows email button when application_email is present', () => {
        render(
            <table>
                <tbody>
                    <DesktopJobRow {...defaultProps} />
                </tbody>
            </table>
        );
        const emailLink = screen.getByTitle(/Email jobs@/);
        expect(emailLink).toBeInTheDocument();
        expect(emailLink.querySelector('.bi-envelope')).toBeInTheDocument();
    });

    it('hides email button when application_email is missing', () => {
        const jobNoEmail = { ...mockJob, application_email: null };
        render(
            <table>
                <tbody>
                    <DesktopJobRow {...defaultProps} job={jobNoEmail} />
                </tbody>
            </table>
        );
        expect(screen.queryByTitle(/Email jobs@/)).not.toBeInTheDocument();
    });

    it('copies details to clipboard when copy button is clicked', () => {
        render(
            <table>
                <tbody>
                    <DesktopJobRow {...defaultProps} />
                </tbody>
            </table>
        );
        const copyBtn = screen.getByTitle('Copy job details');
        fireEvent.click(copyBtn);
        expect(defaultProps.onCopy).toHaveBeenCalledWith(mockJob);
    });

    it('calls onViewAnalysis when analysis button is clicked', () => {
        const onViewAnalysis = vi.fn();
        render(
            <table>
                <tbody>
                    <DesktopJobRow {...defaultProps} onViewAnalysis={onViewAnalysis} />
                </tbody>
            </table>
        );

        const toggleBtn = screen.getByTitle('View match analysis');
        fireEvent.click(toggleBtn);

        expect(onViewAnalysis).toHaveBeenCalledWith(mockJob);
    });

    it('calls onToggleApplied when applied switch is clicked', () => {
        render(
            <table>
                <tbody>
                    <DesktopJobRow {...defaultProps} />
                </tbody>
            </table>
        );
        const switchInput = screen.getByRole('checkbox');
        fireEvent.click(switchInput);
        expect(defaultProps.onToggleApplied).toHaveBeenCalledWith(mockJob);
    });

    it('disables the applied switch while an update is pending', () => {
        render(
            <table>
                <tbody>
                    <DesktopJobRow {...defaultProps} isAppliedPending={true} />
                </tbody>
            </table>
        );

        expect(screen.getByRole('checkbox')).toBeDisabled();
    });

    it('renders top pick badge and workload when present', () => {
        const specializedJob = { ...mockJob, worth_applying: true, workload: 80 };
        render(
            <table>
                <tbody>
                    <DesktopJobRow {...defaultProps} job={specializedJob} />
                </tbody>
            </table>
        );
        expect(screen.getByTitle('Top pick')).toBeInTheDocument();
        expect(screen.getByText('80%')).toBeInTheDocument();
    });

    it('hides every analysis-derived field when the result is not verified', () => {
        const unverifiedJob = { ...mockJob, analysis_verified: false, worth_applying: true };
        render(
            <table><tbody><DesktopJobRow {...defaultProps} job={unverifiedJob} onViewAnalysis={vi.fn()} /></tbody></table>
        );

        expect(screen.queryByText('85%')).not.toBeInTheDocument();
        expect(screen.queryByTitle('Top pick')).not.toBeInTheDocument();
        expect(screen.queryByTitle('View match analysis')).not.toBeInTheDocument();
    });
});
