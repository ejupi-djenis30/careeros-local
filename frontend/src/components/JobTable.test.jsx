import React from 'react';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { JobTable } from './JobTable';
import { renderWithI18n as render } from '../test/renderWithI18n';

const mockRecordView = vi.fn();

// Mock useToast so JobTable can render without a ToastProvider
vi.mock('../context/ToastContext', () => ({
    useToast: () => ({ showToast: vi.fn(), clearToast: vi.fn() })
}));

vi.mock('../services/jobs', () => ({
    JobService: {
        recordView: (...args) => mockRecordView(...args),
    }
}));

// Mock matchMedia for window size
Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation(query => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
    })),
});

describe('JobTable', () => {
    beforeEach(() => {
        mockRecordView.mockReset();
        mockRecordView.mockResolvedValue({});
    });

    it('renders the empty state when no jobs are provided', () => {
        render(<JobTable jobs={[]} isGlobalView={false} onToggleApplied={vi.fn()} pagination={{}} onPageChange={vi.fn()} />);

        expect(screen.getByText("No jobs found")).toBeInTheDocument();
        expect(screen.getByText("Adjust the filters or start a new search.")).toBeInTheDocument();
    });

    it('renders desktop table headers when rendered with jobs', () => {
        const mockJobs = [{
            id: '1', title: 'Software Engineer', company: 'Google', location: 'Zurich',
            affinity_score: 90, match_reason: 'Good match', is_applied: false
        }];

        const mockPagination = {
            page: 1,
            pages: 1,
            total: 1
        };

        render(<JobTable jobs={mockJobs} isGlobalView={false} onToggleApplied={vi.fn()} pagination={mockPagination} onPageChange={vi.fn()} />);

        expect(screen.getByText('Job title')).toBeInTheDocument();
        expect(screen.getByText('Company and location')).toBeInTheDocument();
        expect(screen.getByText('Match details')).toBeInTheDocument();
        expect(screen.getByText('Applied')).toBeInTheDocument();
        expect(screen.getByText('Actions')).toBeInTheDocument();
    });

    it('renders pagination links when pagination prop is present', () => {
        const mockJobs = [{ id: '1', title: 'Job 1', company: 'C1' }];
        const mockPagination = {
            page: 2,
            pages: 5,
            total: 50
        };

        render(<JobTable jobs={mockJobs} isGlobalView={false} onToggleApplied={vi.fn()} pagination={mockPagination} onPageChange={vi.fn()} />);

        expect(screen.getByText('2')).toBeInTheDocument();
        // Match the pagination separator specifically
        expect(screen.getByText((content, element) => content.includes('/') && element.tagName === 'SPAN' && element.className.includes('text-secondary'))).toBeInTheDocument();
        expect(screen.getByText((content) => content.includes('Showing'))).toBeInTheDocument();
        expect(screen.getByText('21-40')).toBeInTheDocument();
        expect(screen.getByText('50')).toBeInTheDocument();
    });

    it('calls onPageChange when next button clicked', () => {
        const mockJobs = [{ id: '1', title: 'Job 1', company: 'C1' }];
        const mockPagination = { page: 1, pages: 2, total: 40 };
        const onPageChange = vi.fn();

        render(<JobTable jobs={mockJobs} pagination={mockPagination} onPageChange={onPageChange} />);

        const nextBtn = document.querySelector('.bi-chevron-right').closest('button');
        fireEvent.click(nextBtn);
        expect(onPageChange).toHaveBeenCalledWith(2);
    });

    it('calls onPageChange when prev button clicked', () => {
        const mockJobs = [{ id: '1', title: 'Job 1', company: 'C1' }];
        const mockPagination = { page: 2, pages: 2, total: 40 };
        const onPageChange = vi.fn();

        render(<JobTable jobs={mockJobs} pagination={mockPagination} onPageChange={onPageChange} />);

        const prevBtn = document.querySelector('.bi-chevron-left').closest('button');
        fireEvent.click(prevBtn);
        expect(onPageChange).toHaveBeenCalledWith(1);
    });

    it('copies job details to clipboard when copy is triggered', async () => {
        const mockJobs = [{
            id: '1', title: 'Software Engineer', company: 'Google', location: 'Zurich',
            description: 'Test desc', external_url: 'http://test.com'
        }];
        const mockPagination = { page: 1, pages: 1, total: 1 };

        const writeTextMock = vi.fn().mockResolvedValue();
        Object.assign(navigator, {
            clipboard: { writeText: writeTextMock }
        });

        render(<JobTable jobs={mockJobs} pagination={mockPagination} onPageChange={vi.fn()} isGlobalView={false} />);

        // Desktop button title is "Copy Details"
        const copyBtn = screen.getByTitle('Copy job details');
        fireEvent.click(copyBtn);

        expect(writeTextMock).toHaveBeenCalled();
        const calledArg = JSON.parse(writeTextMock.mock.calls[0][0]);
        expect(calledArg.title).toBe('Software Engineer');
    });

    it('opens and closes the AI analysis modal', () => {
        const mockJobs = [{
            id: '1', title: 'Engineer', company: 'Google', affinity_analysis: 'Great fit because...', affinity_score: 95, analysis_verified: true
        }];
        const mockPagination = { page: 1, pages: 1, total: 1 };

        render(<JobTable jobs={mockJobs} pagination={mockPagination} onPageChange={vi.fn()} isGlobalView={false} />);

        // Desktop button title is "View Analysis", but it's also in MobileCard
        const viewBtns = screen.getAllByTitle('View match analysis');
        // Mobile is rendered first in DOM, Desktop second
        fireEvent.click(viewBtns[1] || viewBtns[0]);

        expect(mockRecordView).toHaveBeenCalledWith('1');
        expect(screen.getByText('Local match analysis')).toBeInTheDocument();
        expect(screen.getByText('Great fit because...')).toBeInTheDocument();

        const closeBtn = screen.getByText('Close');
        fireEvent.click(closeBtn);

        expect(screen.queryByText('Local match analysis')).not.toBeInTheDocument();
    });

    it('shows validated local-model provenance and inspectable citations', () => {
        const mockJobs = [{
            id: 'grounded-1',
            title: 'Backend Engineer',
            company: 'Local Co',
            affinity_analysis: 'Local evidence review: strong fit.',
            affinity_score: 91,
            analysis_provenance: 'local_model_validated',
            analysis_model_id: 'llama-cpp-local/qwen3-1.7b-q8',
            analysis_contract_version: '1.1.0',
            analysis_verified: true,
            analysis_structured: {
                recommendation: 'strong_fit',
                evidence_citations: [{
                    type: 'skill',
                    assessment: 'strength',
                    job_evidence_id: 'job:0',
                    candidate_evidence_id: 'candidate:profile',
                    job_evidence: 'Requires production Python',
                    candidate_evidence: 'Built production Python services',
                }],
            },
        }];

        render(
            <JobTable
                jobs={mockJobs}
                pagination={{ page: 1, pages: 1, total: 1 }}
                onPageChange={vi.fn()}
                isGlobalView={false}
            />
        );
        fireEvent.click(screen.getAllByTitle('View match analysis')[0]);

        expect(screen.getByTestId('validated-match-evidence')).toBeInTheDocument();
        expect(screen.getByText('Validated local model')).toBeInTheDocument();
        expect(screen.getByText('llama-cpp-local/qwen3-1.7b-q8')).toBeInTheDocument();
        expect(screen.getByText('“Requires production Python”')).toBeInTheDocument();
        expect(screen.getByText('“Built production Python services”')).toBeInTheDocument();
    });

    it('opens modal from mobile view and closes with X icon', () => {
        const mockJobs = [{
            id: '1', title: 'Engineer', company: 'Google', affinity_analysis: 'Great fit...', affinity_score: 95, analysis_verified: true
        }];
        const mockPagination = { page: 1, pages: 1, total: 1 };

        // We wrap in a constrained width to ensure mobile logic if needed, but react testing library renders both.
        render(<JobTable jobs={mockJobs} pagination={mockPagination} onPageChange={vi.fn()} isGlobalView={false} />);

        // Trigger the mobile View Analysis button
        const viewBtns = screen.getAllByTitle('View match analysis');
        fireEvent.click(viewBtns[0]); // Mobile variant is rendered first

        expect(screen.getByText('Local match analysis')).toBeInTheDocument();

        const xIcon = document.querySelector('.bi-x-lg');
        fireEvent.click(xIcon.closest('button'));

        expect(screen.queryByText('Local match analysis')).not.toBeInTheDocument();
    });

    it('logs recordView failures instead of swallowing them silently', async () => {
        const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
        mockRecordView.mockRejectedValueOnce(new Error('network down'));

        render(
            <JobTable
                jobs={[{ id: '99', title: 'Engineer', company: 'Google', affinity_analysis: 'Great fit', affinity_score: 95, analysis_verified: true }]}
                pagination={{ page: 1, pages: 1, total: 1 }}
                onPageChange={vi.fn()}
                isGlobalView={false}
            />
        );

        const viewBtns = screen.getAllByTitle('View match analysis');
        fireEvent.click(viewBtns[0]);

        await waitFor(() => {
            expect(warnSpy).toHaveBeenCalledWith(
                'Failed to record job view for 99',
                expect.any(Error)
            );
        });

        warnSpy.mockRestore();
    });
});
