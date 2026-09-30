import { useState, useEffect } from 'react';
import { useApi } from '../hooks/useApi.jsx';
import { createJob, pollJob, getResult } from '../api/jobs.js';

export default function TTS() {
  const { api } = useApi();
  const [text, setText] = useState('');
  const [selectedVoice, setSelectedVoice] = useState(null);
  const [voices, setVoices] = useState([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [audioUrl, setAudioUrl] = useState(null);
  const [result, setResult] = useState(null);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);

  // Giọng thật từ GET /v1/voices — trước đây gọi 405 nên grid giọng trống trơn.
  useEffect(() => {
    (async () => {
      try {
        const list = await api.get('/v1/voices');
        setVoices(list);
        if (list.length > 0) setSelectedVoice(list[0].id);
      } catch (e) {
        console.error('tải danh sách giọng thất bại', e);
      }
    })();
  }, [api]);

  const generateSpeech = async () => {
    if (!text.trim()) {
      setError('Vui lòng nhập văn bản để tạo giọng nói');
      return;
    }
    setIsGenerating(true);
    setAudioUrl(null);
    setResult(null);
    setJob(null);
    setError(null);
    try {
      const created = await createJob({
        type: 'tts',
        text,
        voice_id: selectedVoice || undefined,
      });
      const done = await pollJob(created.jobId, { onUpdate: setJob, timeoutMs: 10 * 60 * 1000 });
      if (done.status === 'failed') {
        setError(done.error || 'Tạo giọng nói thất bại.');
      } else {
        const res = await getResult(created.jobId);
        setResult(res);
        setAudioUrl(res.url);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '14px', fontWeight: 700 }}>
        Chuyển văn bản thành giọng nói
      </h1>
      <p style={{ color: 'var(--text-dim)', marginBottom: '20px' }}>
        Nhập văn bản, chọn giọng đọc (kể cả giọng bạn đã nhân bản ở trang Giọng Clone) và tạo file âm thanh tiếng Việt tự nhiên
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '20px' }}>
        {/* Left: Editor & Controls */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Text input */}
          <div>
            <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '10px', fontWeight: 600 }}>
              Nhập văn bản
            </label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Xin chào, đây là VoiceVibe. Hãy nhập văn bản bạn muốn chuyển đổi thành giọng nói tại đây..."
              rows={12}
              style={{
                width: '100%',
                padding: '12px',
                borderRadius: 'var(--radius-lg)',
                border: '1px solid var(--border)',
                fontSize: 'var(--text-base)',
                background: 'var(--bg)',
                color: 'var(--text)',
                resize: 'vertical',
                fontFamily: 'inherit',
                lineHeight: 1.6,
              }}
            />
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginTop: '8px', textAlign: 'right' }}>
              {text.length} ký tự
            </div>
          </div>

          {/* Voice selector */}
          <div>
            <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '10px', fontWeight: 600 }}>
              Chọn giọng đọc
            </label>
            {voices.length === 0 ? (
              <div style={{ padding: '12px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
                Chưa có giọng nào — tạo giọng ở trang “Giọng Clone”, hoặc cứ tạo giọng nói với giọng mặc định của hệ thống.
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '12px' }}>
                {voices.map((v) => (
                  <button
                    key={v.id}
                    onClick={() => setSelectedVoice(v.id)}
                    style={{
                      background: selectedVoice === v.id ? 'var(--primary-light)' : 'var(--surface)',
                      border: selectedVoice === v.id ? '1px solid var(--primary)' : '1px solid var(--border)',
                      borderRadius: 'var(--radius)',
                      padding: '10px 12px',
                      textAlign: 'center',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      gap: '8px',
                    }}
                  >
                    <div style={{ fontSize: '20px' }}>🎤</div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                      {v.name}
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>{v.lang}</div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Generate button */}
          <button
            disabled={!text.trim() || isGenerating}
            onClick={generateSpeech}
            style={{
              background: 'var(--gradient)',
              color: '#fff',
              border: 'none',
              padding: '12px 16px',
              borderRadius: 'var(--radius)',
              fontSize: 'var(--text-base)',
              fontWeight: 600,
              cursor: text.trim() && !isGenerating ? 'pointer' : 'not-allowed',
              opacity: text.trim() && !isGenerating ? 1 : 0.6,
              maxWidth: '240px',
            }}
          >
            {isGenerating ? 'Đang tạo giọng nói...' : 'Tạo giọng nói'}
          </button>

          {/* Error */}
          {error && (
            <div style={{
              padding: '12px', borderRadius: 'var(--radius)',
              background: 'var(--danger-light)', color: 'var(--danger)', whiteSpace: 'pre-wrap',
            }}>
              {error}
            </div>
          )}

          {/* Audio player */}
          {audioUrl && (
            <div>
              <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '10px', fontWeight: 600 }}>
                Kết quả
              </label>
              <audio
                controls
                src={audioUrl}
                style={{ width: '100%', outline: 'none' }}
              />
              <a href={result?.url} download={result?.filename} style={{ display: 'inline-block', marginTop: '10px', color: 'var(--primary)', fontWeight: 600 }}>
                Tải về máy ({result?.filename})
              </a>
            </div>
          )}

          {/* Status */}
          {job && job.status !== 'done' && !error && (
            <div style={{ padding: '12px', borderRadius: 'var(--radius)', background: 'var(--info-light)', color: 'var(--info)' }}>
              <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '8px' }}>
                {job.status === 'queued' ? 'Hàng đợi' : job.status === 'running' ? 'Đang xử lý' : job.status}
              </div>
              {job.progress?.percent !== undefined && (
                <div>
                  <div
                    style={{
                      height: '4px',
                      borderRadius: '2px',
                      background: 'var(--info)',
                      width: `${job.progress.percent}%`,
                      transition: 'width 0.6s',
                    }}
                  />
                  <div style={{ fontSize: 'var(--text-xs)', marginTop: '4px' }}>
                    {job.progress.percent.toFixed(1)}%
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right sidebar: waveform placeholder */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Waveform placeholder */}
          <div
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              padding: '14px',
              height: '200px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
              <div style={{ fontSize: '48px', marginBottom: '10px' }}>声波</div>
              <div style={{ fontSize: 'var(--text-sm)' }}>Waveform sẽ hiển thị tại đây sau khi tạo</div>
            </div>
          </div>

          {/* Tips */}
          <div
            style={{
              background: 'var(--info-light)',
              border: '1px solid var(--info)',
              borderRadius: 'var(--radius-lg)',
              padding: '12px',
            }}
          >
            <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '10px', color: 'var(--info)' }}>
              💡 Mẹo
            </h4>
            <ul style={{ fontSize: 'var(--text-sm)', color: 'var(--text)', listStyle: 'none', padding: 0, margin: 0 }}>
              <li style={{ marginBottom: '8px' }}>• Dùng dấu phẩy và dấu chấm để tạo pause tự nhiên</li>
              <li style={{ marginBottom: '8px' }}>• Tạo giọng riêng ở trang “Giọng Clone” từ 5-10 giây mẫu</li>
              <li>• Nghe kết quả ngay tại đây sau khi tạo xong</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
