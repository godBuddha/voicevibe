// GD3 — vitest: adapt.js là lớp chuyển shape backend↔trang duy nhất; sai một
// field là cả trang hiện N/A (đã gặp thật: job.file không tồn tại → nhãn trống).
import { describe, it, expect } from 'vitest';
import { adaptJob, adaptUsage, adaptVoice, adaptUser } from './adapt.js';

describe('adaptJob', () => {
  const j = {
    job_id: 'j1', type: 'dub', status: 'running', progress: 42,
    params: { media_url: 'media/x1/video%20Hop%20nghi.mp4', target_lang: 'vi' },
    result_key: 'jobs/j1/out/result-v1.mp4', error: null,
    created_at: 1794540000, updated_at: 1794540100, revision: 3,
  };

  it('map đủ field + progress object', () => {
    const a = adaptJob(j);
    expect(a.id).toBe('j1');
    expect(a.status).toBe('running');
    expect(a.progress.percent).toBe(42);
    expect(a.revision).toBe(3);
    expect(a.label).toBe('video Hop nghi.mp4'); // tên file decode từ media_url
    expect(a.createdAt).toEqual(new Date(1794540000 * 1000));
  });

  it('label fallback theo text rồi theo loại', () => {
    const b = adaptJob({ job_id: 'j2', type: 'translate', status: 'queued',
                         params: { text: 'Xin chào các bạn rất nhiều' } });
    expect(b.label).toBe('Xin chào các bạn rất nhiều');
    const c = adaptJob({ job_id: 'j3', type: 'stt', status: 'queued', params: {} });
    expect(c.label).toBe('Giọng nói → văn bản');
  });

  it('progress null → 0%, null → null', () => {
    const a = adaptJob({ job_id: 'j', status: 'queued', params: {} });
    expect(a.progress.percent).toBe(0);
    expect(adaptJob(null)).toBeNull();
  });

  it('error + resultKey mang qua', () => {
    const a = adaptJob({ job_id: 'j', status: 'failed', params: {},
                         error: 'ffmpeg thất bại', result_key: 'k.mp4' });
    expect(a.error).toBe('ffmpeg thất bại');
    expect(a.resultKey).toBe('k.mp4');
  });
});

describe('adaptUsage', () => {
  it('map snake_case → camelCase', () => {
    const u = adaptUsage({ total_jobs: 18, running: 2,
                           by_type: { dub: 5 }, by_status: { done: 10 } });
    expect(u).toEqual({ totalJobs: 18, running: 2,
                        breakdown: { dub: 5 }, byStatus: { done: 10 } });
  });
  it('null → số 0 an toàn (không crash dashboard)', () => {
    expect(adaptUsage(null)).toEqual({ totalJobs: 0, running: 0, breakdown: {}, byStatus: {} });
  });
});

describe('adaptVoice / adaptUser', () => {
  it('isClone theo engine vieneu', () => {
    expect(adaptVoice({ id: 'v1', name: 'Giọng A', engine: 'vieneu' }).isClone).toBe(true);
    expect(adaptVoice({ id: 'v2', name: 'VieNeu', engine: 'local' }).isClone).toBe(false);
    expect(adaptVoice(null)).toBeNull();
  });
  it('name fallback phần trước @ của email', () => {
    expect(adaptUser({ user_id: 'u1', email: 'long@x.com' }).name).toBe('long');
    expect(adaptUser({ user_id: 'u1', email: 'a@x.com', name: 'Đức Long' }).name).toBe('Đức Long');
    expect(adaptUser(null)).toBeNull();
  });
});
