import { useState, useRef, useEffect } from 'react';
import { useApi } from '../hooks/useApi.jsx';

export default function STT() {
  const { api } = useApi();
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [transcript, setTranscript] = useState(null);
  const [speakers, setSpeakers] = useState([]);
  const [job, setJob] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const handleFile = (f) => {
    if (f && f.type.startsWith('audio/')) {
      setFile(f);
      setTranscript(null);
      setSpeakers([]);
      setJob(null);
    } else {
      alert('Chỉ hỗ trợ file audio');
    }
  };

  const startSTT = async () => {
    if (!file) return;
    setIsProcessing(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await api.post('/v1/jobs', { body: formData, isMultipart: true });
      setJob({ ...res, status: 'queued', progress: { percent: 0, step: 'Nhận dạng giọng nói', message: 'Đang xử lý audio...' } });
      pollJob(res.id);
    } catch (err) {
      alert('Lỗi khi bắt đầu nhận dạng: ' + err.message);
      setIsProcessing(false);
    }
  };

  const pollJob = async (jobId) => {
    const interval = setInterval(async () => {
      try {
        const j = await api.get(`/v1/jobs/${jobId}`);
        setJob(j);
        if (j.status === 'completed') {
          setIsProcessing(false);
          if (j.result?.transcript) setTranscript(j.result.transcript);
          if (j.result?.speakers) setSpeakers(j.result.speakers);
          clearInterval(interval);
        } else if (j.status === 'failed') {
          setIsProcessing(false);
          alert('Nhận dạng thất bại');
          clearInterval(interval);
        }
      } catch {
        clearInterval(interval);
        setIsProcessing(false);
      }
    }, 2000);
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
        return `${s.id}\n${start} --> ${end}\n${s.text}\n\n`;
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
    <div style={{ padding: '40px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '24px', fontWeight: 700 }}>
        Chuyển giọng nói thành văn bản (STT)
      </h1>
      <p style={{ color: 'var(--text-dim)', marginBottom: '48px' }}>
        Chuyển đổi audio thành văn bản chính xác với nhận dạng người nói
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '40px' }}>
        {/* Left: Upload and transcript */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
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
                gap: '16px',
              }}
            >
              <input
                type="file"
                ref={fileInputRef}
                onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                accept="audio/*"
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
                  <div style={{ fontWeight: 600, marginBottom: '8px' }}>Kéo và thả file audio vào đây</div>
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
                padding: '16px 32px',
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

          {/* Progress */}
          {job && job.status !== 'completed' && (
            <div style={{ padding: '20px', borderRadius: 'var(--radius)', background: 'var(--info-light)', color: 'var(--info)' }}>
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
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>Transcript</h3>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    onClick={() => exportTranscript('txt')}
                    style={{
                      background: 'var(--info-light)',
                      color: 'var(--info)',
                      border: 'none',
                      padding: '8px 16px',
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
                      padding: '8px 16px',
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
                      padding: '8px 16px',
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
                  padding: '24px',
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
              <h3 style={{ fontSize: 'var(--text-xl)', marginBottom: '16px', fontWeight: 700 }}>Nhã dọn người nói</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                {speakers.map((s) => (
                  <div key={s.id} style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
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
                        {Math.floor(s.start / 60)}:{(s.start % 60).toFixed(1)}s - {Math.floor(s.end / 60)}:{(s.end % 60).toFixed(1)}s
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          {/* Tips */}
          <div style={{ background: 'var(--info-light)', border: '1px solid var(--info)', borderRadius: 'var(--radius-lg)', padding: '20px' }}>
            <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '12px', color: 'var(--info)' }}>
              💡 Mẹo
            </h4>
            <ul style={{ fontSize: 'var(--text-sm)', color: 'var(--text)', listStyle: 'none', padding: 0, margin: 0 }}>
              <li style={{ marginBottom: '8px' }}>• Dùng file chất lượng cao, ít tiếng ồn</li>
              <li style={{ marginBottom: '8px' }}>• Hệ thống tự động phát hiện người nói</li>
              <li>• Có thể chỉnh sửa lại transcript sau khi xuất</li>
            </ul>
          </div>

          {/* Features */}
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '20px' }}>
            <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '12px' }}>
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