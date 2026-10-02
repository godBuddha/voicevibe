// B6 — trang "Tóm tắt nội dung": dán văn bản HOẶC chọn video/âm thanh/link →
// hệ tự nghe (nếu cần) rồi tóm tắt bằng AI. Kết quả Markdown kèm mốc giờ
// [hh:mm:ss] để nhảy tới đúng chỗ video. Transcript dài hàng tiếng vẫn được:
// map-reduce từng phần rồi gộp.
import { useRef, useState } from 'react';
import { createJob, pollJob, getResult, uploadMedia } from '../api/jobs.js';

const LANGUAGES = { vi: 'Tiếng Việt', en: 'Tiếng Anh', ja: 'Tiếng Nhật', zh: 'Tiếng Trung' };

// Markdown in đậm/light — không cần thư viện: chỉ chuyển **đậm**, ## đề mục,
// bullet — giữ nguyên mốc [hh:mm:ss] (trả chữ thuần, người dùng copy được).
function mdToHtml(md) {
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const lines = String(md || '').split('\n');
  const out = [];
  for (const raw of lines) {
    const line = esc(raw);
    if (/^#{1,3}\s/.test(line)) out.push(`<h3 style="margin:8px 0 4px">${line.replace(/^#{1,3}\s/, '')}</h3>`);
    else if (/^\s*[-*]\s/.test(line)) out.push(`<li style="margin-left:16px">${line.replace(/^\s*[-*]\s/, '')}</li>`);
    else if (line.trim()) out.push(`<p style="margin:4px 0">${line}</p>`);
  }
  return out.join('\n').replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
}

export default function Summary() {
  const fileRef = useRef(null);
  const [mode, setMode] = useState('text'); // text | file
  const [text, setText] = useState('');
  const [file, setFile] = useState(null);
  const [url, setUrl] = useState('');
  const [target, setTarget] = useState('vi');
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const doSummarize = async () => {
    setError(null);
    setResult(null);
    setBusy(true);
    try {
      const payload = { type: 'summary', target_lang: target };
      if (mode === 'text' && text.trim()) {
        payload.text = text;
      } else if (url.trim()) {
        payload.source_url = url.trim();
      } else if (file) {
        payload.media_url = await uploadMedia(file);
      } else {
        setError('Nhập văn bản, dán link hoặc chọn file.');
        setBusy(false);
        return;
      }
      const created = await createJob(payload);
      const done = await pollJob(created.jobId, {
        onUpdate: setJob, timeoutMs: 45 * 60 * 1000,
      });
      if (done.status === 'failed') {
        setError(done.error || 'Tóm tắt thất bại.');
      } else {
        setResult((await getResult(created.jobId)).content || '');
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const inputStyle = {
    padding: '8px 10px', borderRadius: 'var(--radius)',
    border: '1px solid var(--border)', background: 'var(--bg)',
    color: 'var(--text)', fontSize: 'var(--text-sm)',
  };

  return (
    <div style={{ padding: '20px', maxWidth: '1000px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '10px', fontWeight: 700 }}>
        Tóm tắt nội dung
      </h1>
      <p style={{ color: 'var(--text-dim)', marginBottom: '18px' }}>
        Dán văn bản, chọn video/âm thanh, hoặc dán link — hệ tự nghe rồi tóm
        tắt bằng AI. Video dài cả giờ vẫn được: tóm từng phần rồi gộp. Bản
        tóm tắt kèm mốc [giờ:phút:giây] để nhảy tới đúng chỗ.
      </p>

      <div style={{ display: 'flex', gap: '8px', marginBottom: '14px' }}>
        {[['text', 'Văn bản'], ['file', 'File video/âm thanh']].map(([v, label]) => (
          <button key={v} onClick={() => setMode(v)}
            style={{
              padding: '8px 14px', borderRadius: 'var(--radius)', fontWeight: 600,
              fontSize: 'var(--text-sm)', cursor: 'pointer',
              border: `1px solid ${mode === v ? 'var(--primary)' : 'var(--border)'}`,
              background: mode === v ? 'var(--primary-light)' : 'var(--surface)',
              color: mode === v ? 'var(--primary)' : 'var(--text)',
            }}>
            {label}
          </button>
        ))}
        <button onClick={() => setMode('url')}
          style={{
            padding: '8px 14px', borderRadius: 'var(--radius)', fontWeight: 600,
            fontSize: 'var(--text-sm)', cursor: 'pointer',
            border: `1px solid ${mode === 'url' ? 'var(--primary)' : 'var(--border)'}`,
            background: mode === 'url' ? 'var(--primary-light)' : 'var(--surface)',
            color: mode === 'url' ? 'var(--primary)' : 'var(--text)',
          }}>
          Từ link
        </button>
        <div style={{ flex: 1 }} />
        <select value={target} onChange={(e) => setTarget(e.target.value)} style={inputStyle}>
          {Object.entries(LANGUAGES).map(([v, l]) => (
            <option key={v} value={v}>Tóm tắt bằng {l}</option>
          ))}
        </select>
      </div>

      {mode === 'text' && (
        <textarea
          value={text} onChange={(e) => setText(e.target.value)}
          placeholder="Dán văn bản cần tóm tắt (hội thoại, bài giảng, nội dung họp…)"
          rows={10} style={{
            width: '100%', padding: '12px', borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--border)', background: 'var(--bg)',
            color: 'var(--text)', fontSize: 'var(--text-base)', marginBottom: '14px',
          }} />
      )}
      {mode === 'file' && (
        <div style={{ marginBottom: '14px' }}>
          <input ref={fileRef} type="file" accept="video/*,audio/*"
            onChange={(e) => setFile(e.target.files?.[0] || null)} />
          {file && (
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginTop: '4px' }}>
              {file.name} ({(file.size / 1024 / 1024).toFixed(1)} MB) — hệ sẽ tự nghe trước khi tóm tắt
            </div>
          )}
        </div>
      )}
      {mode === 'url' && (
        <input value={url} onChange={(e) => setUrl(e.target.value)}
          placeholder="https://… (link video)" style={{ ...inputStyle, width: '100%', marginBottom: '14px' }} />
      )}

      <button
        disabled={busy}
        onClick={doSummarize}
        style={{
          background: 'var(--gradient)', color: '#fff', border: 'none',
          padding: '12px 16px', borderRadius: 'var(--radius)', fontWeight: 600,
          fontSize: 'var(--text-base)', cursor: busy ? 'wait' : 'pointer',
          opacity: busy ? 0.6 : 1, maxWidth: '200px',
        }}>
        {busy ? 'Đang tóm tắt…' : 'Tóm tắt ngay'}
      </button>

      {error && (
        <div style={{
          padding: '12px', borderRadius: 'var(--radius)',
          background: 'var(--danger-light)', color: 'var(--danger)',
          whiteSpace: 'pre-wrap', marginTop: '14px',
        }}>
          {error}
        </div>
      )}

      {job && busy && (
        <div style={{
          padding: '12px', borderRadius: 'var(--radius)',
          background: 'var(--info-light)', color: 'var(--info)', marginTop: '14px',
        }}>
          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '8px' }}>
            {job.progress?.message || 'Đang xử lý'} — {job.progress?.percent?.toFixed(1)}%
          </div>
          <div style={{
            height: '4px', borderRadius: '2px', background: 'var(--info)',
            width: `${job.progress?.percent ?? 0}%`, transition: 'width 0.6s',
          }} />
        </div>
      )}

      {result && (
        <div style={{
          border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)',
          padding: '14px', marginTop: '14px', background: 'var(--surface)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
            <h3 style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 700 }}>Bản tóm tắt</h3>
            <div style={{ flex: 1 }} />
            <a href={URL.createObjectURL(new Blob([result], { type: 'text/markdown' }))}
               download="tóm-tắt.md"
               style={{ color: 'var(--primary)', fontWeight: 600, fontSize: 'var(--text-sm)' }}>
              Tải .md
            </a>
          </div>
          <div
            style={{ fontSize: 'var(--text-base)', lineHeight: 1.55 }}
            dangerouslySetInnerHTML={{ __html: mdToHtml(result) }} />
        </div>
      )}
    </div>
  );
}
