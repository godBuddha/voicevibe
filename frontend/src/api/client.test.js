// GD3 — vitest: contract của api client (không jsdom — stub fetch thuần).
// Ba hợp đồng đã từng vỡ trong production: (1) 422 phải mang `detail` tiếng
// Việt thay vì "HTTP 422" vô nghĩa; (2) 401 phải gọi onUnauthorized trước khi
// ném (trang đăng nhập hiện đúng lý do); (3) 204 trả null, không crash parse.
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { api, setOnUnauthorized } from './client.js';

const realFetch = globalThis.fetch;

function stubFetch(status, payload) {
  globalThis.fetch = async () => ({
    status,
    ok: status < 400,
    json: async () => payload,
  });
}

beforeEach(() => { setOnUnauthorized(null); });
afterEach(() => { globalThis.fetch = realFetch; });

describe('api client', () => {
  it('422 ném Error mang detail tiếng Việt', async () => {
    stubFetch(422, { detail: 'bilingual cần target_lang' });
    await expect(api.post('/v1/jobs', { body: {} }))
      .rejects.toThrow('bilingual cần target_lang');
  });

  it('401 gọi onUnauthorized rồi ném detail', async () => {
    let called = 0;
    setOnUnauthorized(() => { called += 1; });
    stubFetch(401, { detail: 'Email hoặc mật khẩu không đúng' });
    await expect(api.post('/v1/auth/login', { body: {} }))
      .rejects.toThrow('Email hoặc mật khẩu không đúng');
    expect(called).toBe(1);
  });

  it('500 không có detail/message → HTTP 500', async () => {
    stubFetch(500, null);
    await expect(api.get('/v1/jobs')).rejects.toThrow('HTTP 500');
  });

  it('204 trả null, không crash', async () => {
    globalThis.fetch = async () => ({ status: 204, ok: true, json: async () => { throw new Error('no body'); } });
    expect(await api.del('/v1/jobs/x')).toBeNull();
  });

  it('200 trả payload nguyên vẹn', async () => {
    stubFetch(200, { job_id: 'abc' });
    expect((await api.get('/v1/jobs/abc')).job_id).toBe('abc');
  });

  it('query được nối vào URL', async () => {
    let seen = '';
    globalThis.fetch = async (url) => { seen = String(url); return { status: 200, ok: true, json: async () => ({}) }; };
    await api.get('/v1/jobs', { query: { limit: 20 } });
    expect(seen).toContain('limit=20');
  });
});
