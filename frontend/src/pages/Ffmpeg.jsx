// GD1 — Bàn điều khiển FFmpeg: gõ yêu cầu bằng lời → "Dịch thành lệnh"
// (preview, KHÔNG chạy) → xem lại lệnh + giải thích + cảnh báo → "Chạy lệnh
// này" (tạo job type=ffmpeg). argv chỉ nhận từ server preview (đã validate
// 5 lớp chặn: binary/URL/device/…/ext) — client không tự chế lệnh.
import { useRef, useState } from 'react';
import { createJob, pollJob, getResult, uploadMedia } from '../api/jobs.js';
import { Terminal, Play, RefreshCw, TriangleAlert, LoaderCircle } from 'lucide-react';

const QUICK = [
  { v: 'Cắt từ 0:30 đến 1:00', label: 'Cắt đoạn' },
  { v: 'Chuyển video thành MP3 320kbps', label: 'Tách nhạc' },
  { v: 'Xuất khung hình đầu tiên thành ảnh PNG', label: 'Lấy ảnh bìa' },
  { v: 'Chuyển video thành WAV 48kHz mono', label: 'Chuyển WAV' },
];

export default function Ffmpeg() {
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [sourceUrl, setSourceUrl] = useState('');
  const [removeSponsor, setRemoveSponsor] = useState(false);
  const [instruction, setInstruction] = useState('');
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState(null); // {command, explanation, warnings, ffmpeg_argv}
  const [running, setRunning] = useState(false);
  const [job, setJob] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const resetAll = () => { setFile(null); setSourceUrl(''); setInstruction(''); setPreview(null); setJob(null); setResult(null); setError(null); };

  const handleFile = (f) => {
    if (f && (f.type.startsWith('video/') || f.type.startsWith('audio/'))) {
      setFile(f); setSourceUrl(''); setPreview(null);
    } else {
      alert('Chỉ hỗ trợ file video hoặc audio');
    }
  };

  const bodySource = async () => {
    // nguồn: upload/link — mỗi lần chọn GỬI ĐÚNG MỘT, preview và chạy dùng
    // CÙNG một nguồn (preview là lệnh của NƯỚC NÀY, đổi nguồn phải dịch lại).
    if (file) return { media_url: await uploadMedia(file) };
    if (sourceUrl.trim()) {
      const body = { source_url: sourceUrl.trim() };
      if (removeSponsor) body.remove_sponsor = true;
      return body;
    }
    throw new Error('Chọn file hoặc dán link trước');
  };

  const doPreview = async () => {
    if (!instruction.trim()) { setError('Gõ yêu cầu bằng lời trước'); return; }
    setPreviewing(true); setPreview(null); setError(null);
    try {
      const src = await bodySource();
      const r = await fetch('/v1/ffmpeg/preview', {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction: instruction.trim(), ...src }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      setPreview(d);
    } catch (e) { setError(e.message); }
    finally { setPreviewing(false); }
  };

  const doRun = async () => {
    if (!preview) return;
    setRunning(true); setJob(null); setResult(null); setError(null);
    try {
      const src = await bodySource();
      const created = await createJob({
        type: 'ffmpeg', ffmpeg_argv: preview.ffmpeg_argv, ...src,
      });
      const done = await pollJob(created.jobId, {
        onUpdate: setJob, timeoutMs: 2 * 60 * 60 * 1000, // encode dài — hẹn 2h
      });
      if (done.status === 'failed') {
        setError(done.error || 'Chạy lệnh thất bại.');
      } else {
        setResult(await getResult(created.jobId));
      }
    } catch (e) { setError(e.message); }
    finally { setRunning(false); }
  };

  const box = { width: '100%', padding: '10px', borderRadius: 'var(--radius)', border: '1px solid var(--border)', fontSize: 'var(--text-sm)', background: 'var(--bg)', color: 'var(--text)', boxSizing: 'border-box' };
  const card = { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '14px' };

  return (
    <div style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '6px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '10px' }}>
        <Terminal size={24} /> Bàn điều khiển FFmpeg
      </h1>
      <p style={{ color: 'var(--text-dim)', marginBottom: '18px', fontSize: 'var(--text-sm)' }}>
        Gõ yêu cầu bằng lời — hệ dịch thành lệnh, bạn xem lại rồi mới chạy. Lệnh chỉ xử lý file của bạn trong thư mục làm việc, không truy cập mạng.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 380px', gap: '16px', alignItems: 'start' }}>
        {/* Cột trái: nguồn + yêu cầu */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={card}>
            <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ color: 'var(--primary)' }}>1</span> Nguồn
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <input
                type="file" ref={fileInputRef} accept="video/*,audio/*" style={{ display: 'none' }}
                onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
              />
              {file ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: 'var(--text-sm)' }}>
                  <span style={{ fontWeight: 600 }}>{file.name}</span>
                  <span style={{ color: 'var(--text-dim)' }}>{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                  <button onClick={() => setFile(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: 'var(--text-xs)' }}>Bỏ file</button>
                </div>
              ) : (
                <div
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => { e.preventDefault(); handleFile(e.dataTransfer.files?.[0]); }}
                  style={{ height: '88px', border: '2px dashed var(--border)', borderRadius: 'var(--radius)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '4px', cursor: 'pointer', fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}
                >
                  <span style={{ fontWeight: 600, color: 'var(--text)' }}>Kéo thả file video/audio</span>
                  <span style={{ fontSize: 'var(--text-xs)' }}>hoặc bấm để chọn (MP4, MOV, MP3…)</span>
                </div>
              )}
              {!file && (
                <input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="…hoặc dán link video (YouTube, TikTok…)" style={box} />
              )}
              {!file && sourceUrl.trim() && (
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: 'var(--text-sm)' }}>
                  <input type="checkbox" checked={removeSponsor} onChange={(e) => setRemoveSponsor(e.target.checked)} style={{ margin: 0 }} />
                  <span>Xoá quảng cáo theo SponsorBlock trước khi chạy (chỉ với link)</span>
                </label>
              )}
            </div>
          </div>

          <div style={card}>
            <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ color: 'var(--primary)' }}>2</span> Yêu cầu bằng lời
            </h3>
            <div style={{ fontSize: '12px', color: 'var(--text-dim)', marginBottom: '10px' }}>
              Nói rõ yêu cầu của bạn và hệ thống sẽ chuyển thành lệnh FFmpeg
            </div>
            <textarea
              value={instruction} onChange={(e) => { setInstruction(e.target.value); setPreview(null); }}
              placeholder="ví dụ: cắt từ 2:00 đến 2:10, xuất MP3 320kbps"
              rows={3} style={{ ...box, resize: 'vertical' }}
            />
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', margin: '8px 0 10px' }}>
              {QUICK.map((q) => (
                <button
                  key={q.v} onClick={() => { setInstruction(q.v); setPreview(null); }}
                  style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: '16px', padding: '5px 10px', fontSize: '12px', color: 'var(--text-dim)', cursor: 'pointer' }}
                >{q.label}</button>
              ))}
            </div>
            <button
              onClick={doPreview} disabled={previewing || running}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: 'var(--primary)', color: '#fff', border: 'none', padding: '8px 14px', borderRadius: 'var(--radius)', fontSize: 'var(--text-sm)', fontWeight: 600, cursor: 'pointer' }}
            >
              {previewing ? <LoaderCircle size={15} style={{ animation: 'spin 1s linear infinite' }} /> : <Terminal size={15} />}
              {previewing ? 'Đang dịch…' : 'Dịch thành lệnh'}
            </button>
            <div style={{ marginTop: '6px', fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
              Đổi nguồn hoặc sửa yêu cầu → cần bấm dịch lại (nút Chạy tự khóa).
            </div>
          </div>

          {job && (
            <div style={card}>
              <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: '8px' }}>Tiến độ</h3>
              <div style={{ height: '6px', background: 'var(--bg)', borderRadius: '4px', overflow: 'hidden' }}>
                <div style={{ width: `${job.progress?.percent || 0}%`, height: '100%', background: 'var(--primary)', transition: 'width .5s' }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '6px', fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                <span>{job.progress?.message || ''}</span><span>{job.progress?.percent || 0}%</span>
              </div>
            </div>
          )}
          {error && (
            <div style={{ padding: '10px', borderRadius: 'var(--radius)', background: 'var(--danger-light)', color: 'var(--danger)', fontSize: 'var(--text-sm)', whiteSpace: 'pre-wrap' }}>{error}</div>
          )}
        </div>

        {/* Cột phải: kết quả dịch */}
        <div style={{ ...card, position: 'sticky', top: '16px' }}>
          <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: '10px' }}>Kết quả dịch</h3>
          {preview ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginBottom: '4px' }}>Lệnh hệ thống sẽ chạy</div>
                <pre style={{ background: '#1e293b', color: '#e2e8f0', padding: '10px', borderRadius: 'var(--radius)', fontSize: '12px', whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: 0 }}>
{preview.command || preview.ffmpeg_argv.join(' ')}
                </pre>
              </div>
              {preview.explanation && (
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>{preview.explanation}</div>
              )}
              {preview.warnings?.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  {preview.warnings.map((w, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: 'var(--text-xs)', color: 'var(--warning, #f59e0b)', background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '6px 8px' }}>
                      <TriangleAlert size={13} /> {w}
                    </div>
                  ))}
                </div>
              )}
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  onClick={doRun} disabled={running}
                  style={{ flex: 1, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '6px', background: running ? 'var(--border)' : 'var(--primary)', color: '#fff', border: 'none', padding: '8px 12px', borderRadius: 'var(--radius)', fontSize: 'var(--text-sm)', fontWeight: 600, cursor: running ? 'default' : 'pointer' }}
                >
                  {running ? <LoaderCircle size={15} style={{ animation: 'spin 1s linear infinite' }} /> : <Play size={15} />}
                  {running ? 'Đang chạy…' : 'Chạy lệnh này'}
                </button>
                <button
                  onClick={doPreview} disabled={previewing || running}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', background: 'var(--bg)', color: 'var(--text)', border: '1px solid var(--border)', padding: '8px 10px', borderRadius: 'var(--radius)', fontSize: 'var(--text-sm)', cursor: 'pointer' }}
                ><RefreshCw size={13} /> Dịch lại</button>
              </div>
            </div>
          ) : (
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
              Chưa có lệnh — điền nguồn + yêu cầu rồi bấm «Dịch thành lệnh». Lệnh hiện ra ở đây để bạn kiểm tra trước khi chạy.
            </div>
          )}
          {result && (
            <div style={{ marginTop: '12px' }}>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginBottom: '4px' }}>Kết quả</div>
              {result.url ? (
                <audio controls src={result.url} style={{ width: '100%' }} />
              ) : null}
              {result.kind !== 'text' && <video controls src={result.url} style={{ width: '100%', borderRadius: 'var(--radius)' }} />}
              <a href={result.url} download style={{ fontSize: 'var(--text-xs)', fontWeight: 600 }}>Tải kết quả về máy</a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
