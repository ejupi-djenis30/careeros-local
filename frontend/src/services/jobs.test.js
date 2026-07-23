import { describe, it, expect, vi, afterEach } from 'vitest';
import { ApiClient } from '../lib/client';
import { JobService } from './jobs';

describe('JobService', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ── getAll ─────────────────────────────────────────────────────────────────

  it('getAll fetches /jobs/ without filters', async () => {
    const mockGet = vi.spyOn(ApiClient, 'get').mockResolvedValue({ items: [], total: 0, page: 1, pages: 1 });
    await JobService.getAll();
    expect(mockGet).toHaveBeenCalledWith('/jobs/', undefined);
  });

  it('getAll appends defined filters as query params', async () => {
    const mockGet = vi.spyOn(ApiClient, 'get').mockResolvedValue({ items: [] });
    await JobService.getAll({ min_score: 70, worth_applying: true });
    const url = mockGet.mock.calls[0][0];
    expect(url).toContain('min_score=70');
    expect(url).toContain('worth_applying=true');
  });

  it('getAll skips null/empty filter values', async () => {
    const mockGet = vi.spyOn(ApiClient, 'get').mockResolvedValue({ items: [] });
    await JobService.getAll({ min_score: null, max_score: '', sort_by: undefined });
    const url = mockGet.mock.calls[0][0];
    expect(url).toBe('/jobs/');
  });

  it('getAll passes signal to ApiClient.get', async () => {
    const mockGet = vi.spyOn(ApiClient, 'get').mockResolvedValue({ items: [] });
    const ctrl = new AbortController();
    await JobService.getAll({}, ctrl.signal);
    expect(mockGet.mock.calls[0][1]).toBe(ctrl.signal);
  });

  it('getAll returns the full response object', async () => {
    vi.spyOn(ApiClient, 'get').mockResolvedValue({ items: [{ id: 1 }], total: 1, page: 1, pages: 1 });
    const res = await JobService.getAll();
    expect(res.total).toBe(1);
    expect(res.items[0].id).toBe(1);
  });

  // ── toggleApplied ──────────────────────────────────────────────────────────

  it('toggleApplied sends PATCH with applied flag', async () => {
    const mockPatch = vi.spyOn(ApiClient, 'patch').mockResolvedValue({ id: 5, applied: true });
    await JobService.toggleApplied(5, true);
    expect(mockPatch).toHaveBeenCalledWith('/jobs/5', { applied: true });
  });

  it('toggleApplied can unapply', async () => {
    const mockPatch = vi.spyOn(ApiClient, 'patch').mockResolvedValue({ id: 5, applied: false });
    await JobService.toggleApplied(5, false);
    expect(mockPatch).toHaveBeenCalledWith('/jobs/5', { applied: false });
  });

  // ── dismiss ────────────────────────────────────────────────────────────────

  it('dismiss sends POST with feedback_signal', async () => {
    const mockPost = vi.spyOn(ApiClient, 'post').mockResolvedValue({});
    await JobService.dismiss(3, 'bad_salary');
    expect(mockPost).toHaveBeenCalledWith('/jobs/3/dismiss', { feedback_signal: 'bad_salary' });
  });

  it('dismiss sends null feedback_signal when not provided', async () => {
    const mockPost = vi.spyOn(ApiClient, 'post').mockResolvedValue({});
    await JobService.dismiss(3);
    expect(mockPost).toHaveBeenCalledWith('/jobs/3/dismiss', { feedback_signal: null });
  });

  // ── reactivate ─────────────────────────────────────────────────────────────

  it('reactivate sends PATCH with dismissed: false', async () => {
    const mockPatch = vi.spyOn(ApiClient, 'patch').mockResolvedValue({});
    await JobService.reactivate(7);
    expect(mockPatch).toHaveBeenCalledWith('/jobs/7', { dismissed: false });
  });

  // ── recordView ─────────────────────────────────────────────────────────────

  it('recordView sends POST to view endpoint', async () => {
    const mockPost = vi.spyOn(ApiClient, 'post').mockResolvedValue({});
    await JobService.recordView(9);
    expect(mockPost).toHaveBeenCalledWith('/jobs/9/view', {});
  });
});
