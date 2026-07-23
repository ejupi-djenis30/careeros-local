import { describe, it, expect, vi, afterEach } from 'vitest';
import { ApiClient } from '../lib/client';
import { SearchService } from './search';

describe('SearchService', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ── start ──────────────────────────────────────────────────────────────────

  it('start sends POST to /search/start with profile body', async () => {
    const mockPost = vi.spyOn(ApiClient, 'post').mockResolvedValue({ task_id: 'abc' });
    const profile = { id: 1, name: 'Dev search' };
    await SearchService.start(profile);
    expect(mockPost).toHaveBeenCalledWith('/search/start', profile, { suppressGlobalError: true });
  });

  // ── getStatus ──────────────────────────────────────────────────────────────

  it('getStatus fetches status for a profile id', async () => {
    const mockGet = vi.spyOn(ApiClient, 'get').mockResolvedValue({ status: 'running' });
    const result = await SearchService.getStatus(42);
    expect(mockGet).toHaveBeenCalledWith('/search/status/42');
    expect(result.status).toBe('running');
  });

  // ── getAllStatuses ──────────────────────────────────────────────────────────

  it('getAllStatuses fetches all statuses with optional signal', async () => {
    const mockGet = vi.spyOn(ApiClient, 'get').mockResolvedValue([]);
    const ctrl = new AbortController();
    await SearchService.getAllStatuses(ctrl.signal);
    expect(mockGet).toHaveBeenCalledWith('/search/status/all', ctrl.signal);
  });

  it('getAllStatuses works without a signal', async () => {
    const mockGet = vi.spyOn(ApiClient, 'get').mockResolvedValue([]);
    await SearchService.getAllStatuses();
    expect(mockGet).toHaveBeenCalledWith('/search/status/all', undefined);
  });

  // ── getProfiles ────────────────────────────────────────────────────────────

  it('getProfiles fetches profiles list with cancellable request options', async () => {
    const mockGet = vi.spyOn(ApiClient, 'get').mockResolvedValue([{ id: 1 }]);
    const controller = new AbortController();
    const profiles = await SearchService.getProfiles({ signal: controller.signal });
    expect(mockGet).toHaveBeenCalledWith('/profiles/', undefined, { signal: controller.signal });
    expect(profiles[0].id).toBe(1);
  });

  // ── uploadCV ──────────────────────────────────────────────────────────────

  it('uploadCV wraps file in FormData and calls postMultipart', async () => {
    const mockMultipart = vi.spyOn(ApiClient, 'postMultipart').mockResolvedValue({ cv_text: 'extracted' });
    const fakeFile = new File(['resume content'], 'cv.pdf', { type: 'application/pdf' });
    await SearchService.uploadCV(fakeFile);
    expect(mockMultipart).toHaveBeenCalledTimes(1);
    const [url, formData] = mockMultipart.mock.calls[0];
    expect(url).toBe('/search/upload-cv');
    expect(formData.get('file')).toBe(fakeFile);
  });

  // ── toggleSchedule ─────────────────────────────────────────────────────────

  it('toggleSchedule sends enabled flag without interval when null', async () => {
    const mockPatch = vi.spyOn(ApiClient, 'patch').mockResolvedValue({});
    await SearchService.toggleSchedule(5, true, null);
    expect(mockPatch).toHaveBeenCalledWith('/profiles/5/schedule', { enabled: true });
  });

  it('toggleSchedule includes interval_hours when provided', async () => {
    const mockPatch = vi.spyOn(ApiClient, 'patch').mockResolvedValue({});
    await SearchService.toggleSchedule(5, true, 12);
    expect(mockPatch).toHaveBeenCalledWith('/profiles/5/schedule', { enabled: true, interval_hours: 12 });
  });

  it('toggleSchedule can disable a schedule', async () => {
    const mockPatch = vi.spyOn(ApiClient, 'patch').mockResolvedValue({});
    await SearchService.toggleSchedule(5, false);
    expect(mockPatch).toHaveBeenCalledWith('/profiles/5/schedule', { enabled: false });
  });

  // ── deleteProfile ──────────────────────────────────────────────────────────

  it('deleteProfile sends DELETE to profile endpoint', async () => {
    const mockDelete = vi.spyOn(ApiClient, 'delete').mockResolvedValue({});
    await SearchService.deleteProfile(3);
    expect(mockDelete).toHaveBeenCalledWith('/profiles/3');
  });

  // ── stopSearch ─────────────────────────────────────────────────────────────

  it('stopSearch sends POST to stop endpoint', async () => {
    const mockPost = vi.spyOn(ApiClient, 'post').mockResolvedValue({ stopped: true });
    await SearchService.stopSearch(7);
    expect(mockPost).toHaveBeenCalledWith('/search/stop/7');
  });
});
