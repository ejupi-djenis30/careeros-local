import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { JobTable } from './JobTable';

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
        expect(screen.getByText("Try adjusting your filters or starting a new search to find opportunities.")).toBeInTheDocument();
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

        expect(screen.getByText('Job Title')).toBeInTheDocument();
        expect(screen.getByText('Company & Location')).toBeInTheDocument();
        expect(screen.getByText('Match & Details')).toBeInTheDocument();
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
        const copyBtn = screen.getByTitle('Copy Details');
        fireEvent.click(copyBtn);

        expect(writeTextMock).toHaveBeenCalled();
        const calledArg = JSON.parse(writeTextMock.mock.calls[0][0]);
        expect(calledArg.title).toBe('Software Engineer');
    });

    it('opens and closes the AI analysis modal', () => {
        const mockJobs = [{
            id: '1', title: 'Engineer', company: 'Google', affinity_analysis: 'Great fit because...', affinity_score: 95
        }];
        const mockPagination = { page: 1, pages: 1, total: 1 };

        render(<JobTable jobs={mockJobs} pagination={mockPagination} onPageChange={vi.fn()} isGlobalView={false} />);

        // Desktop button title is "View Analysis", but it's also in MobileCard
        const viewBtns = screen.getAllByTitle('View Analysis');
        // Mobile is rendered first in DOM, Desktop second
        fireEvent.click(viewBtns[1] || viewBtns[0]);

        expect(mockRecordView).toHaveBeenCalledWith('1');
        expect(screen.getByText('Analisi locale del match')).toBeInTheDocument();
        expect(screen.getByText('Great fit because...')).toBeInTheDocument();

        const closeBtn = screen.getByText('Close');
        fireEvent.click(closeBtn);

        expect(screen.queryByText('Analisi locale del match')).not.toBeInTheDocument();
    });

    it('opens modal from mobile view and closes with X icon', () => {
        const mockJobs = [{
            id: '1', title: 'Engineer', company: 'Google', affinity_analysis: 'Great fit...', affinity_score: 95
        }];
        const mockPagination = { page: 1, pages: 1, total: 1 };

        // We wrap in a constrained width to ensure mobile logic if needed, but react testing library renders both.
        render(<JobTable jobs={mockJobs} pagination={mockPagination} onPageChange={vi.fn()} isGlobalView={false} />);

        // Trigger the mobile View Analysis button
        const viewBtns = screen.getAllByTitle('View Analysis');
        fireEvent.click(viewBtns[0]); // Mobile variant is rendered first

        expect(screen.getByText('Analisi locale del match')).toBeInTheDocument();

        const xIcon = document.querySelector('.bi-x-lg');
        fireEvent.click(xIcon.closest('button'));

        expect(screen.queryByText('Analisi locale del match')).not.toBeInTheDocument();
    });

    it('logs recordView failures instead of swallowing them silently', async () => {
        const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
        mockRecordView.mockRejectedValueOnce(new Error('network down'));

        render(
            <JobTable
                jobs={[{ id: '99', title: 'Engineer', company: 'Google', affinity_analysis: 'Great fit', affinity_score: 95 }]}
                pagination={{ page: 1, pages: 1, total: 1 }}
                onPageChange={vi.fn()}
                isGlobalView={false}
            />
        );

        const viewBtns = screen.getAllByTitle('View Analysis');
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
