// B1 — trang "Tải video từ link": dán URL → xem trước → tải về dùng lại cho
// mọi job (dub/phụ đề/tóm tắt). Lỗi từ yt-dlp đã được backend dịch thành tiếng
// Việt có gợi ý hành động (ERROR_MAP) — hiển thị nguyên văn cho người dùng.
import { useState } from 'react';
import { createJob, downloadPreview, pollJob } from '../api/jobs.js';

const QUALITIES = [
  { v: '1080', label: '1080p — tốt nhất' },
  { v: '720', label: '720p — vừa' },
  { v: '480', label: '480p — nhỏ' },
  { v: 'audio', label: 'Chỉ lấy âm thanh (MP3)' },
];

const fmtDur = (s) => {
  if (!s && s !== 0) return '';
  const m = Math.floor(s / 60), h = Math.floor(s / 3600);
  return h > 0 ? `${h} giờ ${m % 60} phút` : `${m} phút ${Math.floor(s % 60)} giây`;
};

export default function Download() {
  const [url, setUrl] = useState('');
  const [quality, setQuality] = useState('1080');
  const [preview, setPreview] = useState(null);
  const [probing, setProbing] = useState(false);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);

  const doPreview = async () => {
    if (!url.trim()) return;
    setProbing(true);
    setPreview(null);
    setError(null);
    try {
      setPreview(await downloadPreview(url.trim()));
    } catch (e) {
      setError(e.message);
    } finally {
      setProbing(false);
    }
  };

  const doDownload = async () => {
    setError(null);
    setJob(null);
    try {
      const created = await createJob({
        type: 'download', source_url: url.trim(), quality,
      });
      const done = await pollJob(created.jobId, {
        onUpdate: setJob, timeoutMs: 45 * 60 * 1000,
      });
      if (done.status === 'failed') setError(done.error || 'Tải video thất bại.');
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div style={{ padding: '20px', maxWidth: '900px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '10px', fontWeight: 700 }}>
        Tải video từ link
      </h1>
      <p style={{ color: 'var(--text-dim)', marginBottom: '18px' }}>
        Dán link video (YouTube, TikTok, Facebook…) — hệ tải về kho để dùng lại
        cho Lồng tiếng / Phụ đề / Tóm tắt. Giới hạn: video dài tối đa 2 giờ.
      </p>

      <div style={{ display: 'flex', gap: '10px', marginBottom: '14px' }}>
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && doPreview()}
          placeholder="https://…"
          style={{
            flex: 1, padding: '10px 12px', borderRadius: 'var(--radius)',
            border: '1px solid var(--border)', background: 'var(--bg)',
            color: 'var(--text)', fontSize: 'var(--text-base)',
          }}
        />
        <button
          disabled={!url.trim() || probing}
          onClick={doPreview}
          style={{
            background: 'var(--surface)', color: 'var(--text)',
            border: '1px solid var(--border)', padding: '10px 16px',
            borderRadius: 'var(--radius)', fontWeight: 600, cursor: 'pointer',
          }}
        >
          {probing ? 'Đang xem…' : 'Xem trước'}
        </button>
      </div>

      {preview && (
        <div style={{
          display: 'flex', gap: '14px', alignItems: 'center', marginBottom: '14px',
          border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)',
          padding: '12px', background: 'var(--surface)',
        }}>
          {preview.thumbnail && (
            <img src={preview.thumbnail} alt="" referrerPolicy="no-referrer"
                 style={{ width: '160px', borderRadius: 'var(--radius)' }} />
          )}
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 600, marginBottom: '4px', overflow: 'hidden',
                          textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {preview.title}
            </div>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
              {preview.uploader}{fmtDur(preview.duration) && ` — ${fmtDur(preview.duration)}`}
            </div>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '16px' }}>
        <label style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', fontWeight: 600 }}>
          Chất lượng
        </label>
        <select
          value={quality}
          onChange={(e) => setQuality(e.target.value)}
          style={{
            padding: '8px 12px', borderRadius: 'var(--radius)',
            border: '1px solid var(--border)', background: 'var(--bg)',
            color: 'var(--text)', fontSize: 'var(--text-sm)',
          }}
        >
          {QUALITIES.map((q) => (
            <option key={q.v} value={q.v}>{q.label}</option>
          ))}
        </select>
        <button
          disabled={!url.trim()}
          onClick={doDownload}
          style={{
            background: 'var(--gradient)', color: '#fff', border: 'none',
            padding: '10px 18px', borderRadius: 'var(--radius)', fontWeight: 600,
            cursor: url.trim() ? 'pointer' : 'not-allowed',
            opacity: url.trim() ? 1 : 0.6,
          }}
        >
          {job && job.status === 'running' ? 'Đang tải…' : 'Bắt đầu tải'}
        </button>
      </div>

      {error && (
        <div style={{
          padding: '12px', borderRadius: 'var(--radius)',
          background: 'var(--danger-light)', color: 'var(--danger)',
          whiteSpace: 'pre-wrap', marginBottom: '12px',
        }}>
          {error}
        </div>
      )}

      {job && job.status === 'running' && job.progress && (
        <div style={{
          padding: '12px', borderRadius: 'var(--radius)',
          background: 'var(--info-light)', color: 'var(--info)',
        }}>
          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '8px' }}>
            Đang tải {job.progress.percent.toFixed(1)}% — {job.progress.message}
          </div>
          <div style={{
            height: '4px', borderRadius: '2px', background: 'var(--info)',
            width: `${job.progress.percent}%`, transition: 'width 0.6s',
          }} />
        </div>
      )}

      {job && job.status === 'done' && (
        <div style={{
          padding: '12px', borderRadius: 'var(--radius)',
          background: 'var(--success-light)', color: 'var(--success)',
        }}>
          ✅ Đã tải về kho. File nằm trong trang Jobs — mở job để tải xuống, hoặc
          chọn lại file này khi tạo job Lồng tiếng / Phụ đề / Tóm tắt.
        </div>
      )}

      <div style={{
        background: 'var(--info-light)', border: '1px solid var(--info)',
        borderRadius: 'var(--radius-lg)', padding: '12px', marginTop: '16px',
      }}>
        <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '8px', color: 'var(--info)' }}>
          💡 Mẹo
        </h4>
        <ul style={{ fontSize: 'var(--text-sm)', listStyle: 'none', padding: 0, margin: 0 }}>
          <li style={{ marginBottom: '6px' }}>• Video riêng tư / giới hạn độ tuổi cần cookies: quản trị viên cấu hình ở Cài đặt → Tải video từ link</li>
          <li>• Bị chặn khu vực? Cấu hình proxy cùng chỗ đó</li>
        </ul>
      </div>
    </div>
  );
}
