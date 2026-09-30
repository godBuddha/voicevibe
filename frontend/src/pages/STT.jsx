import { useState, useRef } from 'react';
import { useApi } from '../hooks/useApi.jsx';
import { uploadMedia, createJob, pollJob, getResult, parseSrt } from '../api/jobs.js';

export default function STT() {
  const { api } = useApi();
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [transcript, setTranscript] = useState(null);
  const [speakers, setSpeakers] = useState([]);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const handleFile = (f) => {
    if (f && (f.type.startsWith('audio/') || f.type.startsWith('video/'))) {
      setFile(f);
      setTranscript(null);
      setSpeakers([]);
      setJob(null);
      setError(null);
    } else {
      alert('Chỉ hỗ trợ file audio hoặc video');
    }
  };

  const startSTT = async () => {
    if (!file) return;
    setIsProcessing(true);
    setError(null);
    try {
      // Chuẩn thật: file → /v1/media/upload → media_url; job JSON có `type`.
      // (Trước đây nộp multipart không `type` → 422, nút bấm thành cờ mờ.)
      const media_url = await uploadMedia(file);
      const created = await createJob({ type: 'stt', media_url });
      // Lần đầu chạy sẽ tải model nhận dạng (~3GB) — hẹn giờ rộng.
      const done = await pollJob(created.jobId, {
        onUpdate: setJob,
        timeoutMs: 30 * 60 * 1000,
      });
      if (done.status === 'failed') {
        setError(done.error || 'Nhận dạng thất bại.');
      } else {
        const res = await getResult(created.jobId);
        // Kết quả là file SRT thật — phân tích để có transcript + người nói
        // (trước đây đọc j.result.transcript — field không tồn tại bao giờ).
        const cues = parseSrt(res.content || '');
        setTranscript(cues.map((c) => c.text).join('\n'));
        setSpeakers(cues.map((c, i) => ({
          id: i + 1, speaker: c.speaker || '', start: c.start, end: c.end, text: c.text,
        })));
        if (!cues.length) {
          setError('Không nhận dạng được lời nói nào trong file (chỉ có nhạc/tiếng ồn?) — job đã chạy xong, không mất gì.');
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsProcessing(false);
    }
  };

  const fmtClock = (s) => {
    const mm = Math.floor(s / 60);
    const ss = (s % 60).toFixed(1);
    return `${mm}:${ss.padStart(4, '0')}s`;
  };

  const exportTranscript = (format) => {
    if (!transcript) return;
    const name = file?.name?.replace(/\.[^.]+$/, '') || 'transcript';
    let content = '';
    if (format === 'txt') {
      content = transcript;
    } else if (format === 'srt') {
      content = speakers.map((s) => {
        const start = `00:${Math.floor(s.start / 60).toString().padStart(2, '0')}:${(s.start % 60).toFixed(3).padStart(6, '0').replace('.', ',')}`;
        const end = `00:${Math.floor(s.end / 60).toString().padStart(2, '0')}:${(s.end % 60).toFixed(3).padStart(6, '0').replace('.', ',')}`;
        return `${s.id}\n${start} --> ${end}\n${s.speaker ? `[${s.speaker}] ` : ''}${s.text}\n\n`;
      }).join('');
    }
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${name}.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '14px', fontWeight: 700 }}>
        Chuyển giọng nói thành văn bản (STT)
      </h1>
      <p style={{ color: 'var(--text-dim)', marginBottom: '20px' }}>
        Chuyển đổi audio thành văn bản chính xác với nhận dạng người nói
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '20px' }}>
        {/* Left: Upload and transcript */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Upload */}
          {!transcript && (
            <div
              onDragOver={(e) => e.preventDefault()}
              onDragEnter={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (e.dataTransfer.files?.[0]) handleFile(e.dataTransfer.files[0]);
              }}
              onClick={() => fileInputRef.current?.click()}
              style={{
                border: '2px dashed var(--border)',
                borderRadius: 'var(--radius-lg)',
                padding: '64px',
                textAlign: 'center',
                cursor: 'pointer',
                background: 'var(--surface)',
                minHeight: '280px',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '12px',
              }}
            >
              <input
                type="file"
                ref={fileInputRef}
                onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                accept="audio/*,video/*"
                style={{ display: 'none' }}
              />
              <div style={{ fontSize: '64px' }}>🎙️</div>
              {file ? (
                <div>
                  <div style={{ fontWeight: 600, marginBottom: '8px' }}>{file.name}</div>
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                    {(file.size / 1024 / 1024).toFixed(2)} MB
                  </div>
                </div>
              ) : (
                <div>
                  <div style={{ fontWeight: 600, marginBottom: '8px' }}>Kéo và thả file audio/video vào đây</div>
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                    Hoặc nhấn để chọn file (MP3, WAV, M4A, AAC)
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Start button */}
          {!transcript && file && (
            <button
              disabled={isProcessing}
              onClick={startSTT}
              style={{
                background: 'var(--gradient)',
                color: '#fff',
                border: 'none',
                padding: '12px 16px',
                borderRadius: 'var(--radius)',
                fontSize: 'var(--text-base)',
                fontWeight: 600,
                cursor: isProcessing ? 'not-allowed' : 'pointer',
                opacity: isProcessing ? 0.6 : 1,
                alignSelf: 'flex-start',
                maxWidth: '320px',
              }}
            >
              {isProcessing ? 'Đang nhận dạng...' : 'Bắt đầu nhận dạng'}
            </button>
          )}

          {/* Error */}
          {error && (
            <div style={{
              padding: '12px', borderRadius: 'var(--radius)',
              background: 'var(--danger-light)', color: 'var(--danger)', whiteSpace: 'pre-wrap',
            }}>
              {error}
            </div>
          )}

          {/* Progress */}
          {job && job.status !== 'done' && !error && (
            <div style={{ padding: '12px', borderRadius: 'var(--radius)', background: 'var(--info-light)', color: 'var(--info)' }}>
              <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '8px' }}>
                {job.status === 'queued' ? 'Hàng đợi' : job.status === 'running' ? 'Đang xử lý' : job.status}
              </div>
              {job.progress?.message && (
                <div style={{ fontSize: 'var(--text-sm)', marginBottom: '8px' }}>{job.progress.message}</div>
              )}
              {job.progress?.percent !== undefined && (
                <div>
                  <div
                    style={{
                      height: '6px',
                      borderRadius: '3px',
                      background: 'var(--info)',
                      width: `${job.progress.percent}%`,
                      transition: 'width 0.6s',
                    }}
                  />
                  <div style={{ fontSize: 'var(--text-xs)', marginTop: '8px' }}>
                    {job.progress.percent.toFixed(1)}%
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Transcript result */}
          {transcript && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h3 style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>Transcript</h3>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    onClick={() => exportTranscript('txt')}
                    style={{
                      background: 'var(--info-light)',
                      color: 'var(--info)',
                      border: 'none',
                      padding: '8px 12px',
                      borderRadius: 'var(--radius)',
                      fontSize: 'var(--text-sm)',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Xuất TXT
                  </button>
                  <button
                    onClick={() => exportTranscript('srt')}
                    style={{
                      background: 'var(--info-light)',
                      color: 'var(--info)',
                      border: 'none',
                      padding: '8px 12px',
                      borderRadius: 'var(--radius)',
                      fontSize: 'var(--text-sm)',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Xuất SRT
                  </button>
                  <button
                    onClick={() => {
                      setTranscript(null);
                      setFile(null);
                      setJob(null);
                    }}
                    style={{
                      background: 'var(--bg)',
                      color: 'var(--text-dim)',
                      border: '1px solid var(--border)',
                      padding: '8px 12px',
                      borderRadius: 'var(--radius)',
                      fontSize: 'var(--text-sm)',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Xử lý mới
                  </button>
                </div>
              </div>
              <div
                style={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-lg)',
                  padding: '14px',
                  maxHeight: '400px',
                  overflow: 'auto',
                  fontSize: 'var(--text-base)',
                  lineHeight: 1.8,
                }}
                className="scrollbar-thin"
              >
                {transcript}
              </div>
            </div>
          )}

          {/* Speakers */}
          {speakers.length > 0 && (
            <div>
              <h3 style={{ fontSize: 'var(--text-xl)', marginBottom: '12px', fontWeight: 700 }}>Nhãn người nói</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {speakers.map((s) => (
                  <div key={s.id} style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                    <div
                      style={{
                        width: '36px',
                        height: '36px',
                        borderRadius: 'var(--radius-full)',
                        background: 'var(--primary-light)',
                        color: 'var(--primary)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontWeight: 600,
                        fontSize: 'var(--text-sm)',
                        flexShrink: 0,
                      }}
                    >
                      {s.speaker || 'N'}{s.index}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginBottom: '4px' }}>
                        {fmtClock(s.start)} - {fmtClock(s.end)}
                      </div>
                      <div style={{ fontSize: 'var(--text-base)', lineHeight: 1.6 }}>{s.text}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Tips */}
          <div style={{ background: 'var(--info-light)', border: '1px solid var(--info)', borderRadius: 'var(--radius-lg)', padding: '12px' }}>
            <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '10px', color: 'var(--info)' }}>
              💡 Mẹo
            </h4>
            <ul style={{ fontSize: 'var(--text-sm)', color: 'var(--text)', listStyle: 'none', padding: 0, margin: 0 }}>
              <li style={{ marginBottom: '8px' }}>• Dùng file chất lượng cao, ít tiếng ồn</li>
              <li style={{ marginBottom: '8px' }}>• Hệ thống tự động phát hiện người nói</li>
              <li>• Có thể chỉnh sửa lại transcript sau khi xuất</li>
            </ul>
          </div>

          {/* Features */}
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '12px' }}>
            <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '10px' }}>
              🎯 Tính năng
            </h4>
            <ul style={{ fontSize: 'var(--text-sm)', color: 'var(--text)', listStyle: 'none', padding: 0, margin: 0 }}>
              <li style={{ marginBottom: '8px' }}>• Nhận dạng tiếng Việt chính xác</li>
              <li style={{ marginBottom: '8px' }}>• Phân biệt nhiều người nói</li>
              <li style={{ marginBottom: '8px' }}>• Xuất định dạng SRT, TXT</li>
              <li>• Hiển thị thời gian từng đoạn</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}