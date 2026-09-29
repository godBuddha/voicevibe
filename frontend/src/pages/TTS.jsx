import { useState, useEffect } from 'react';
import { useApi } from '../hooks/useApi.jsx';
import { useAuth } from '../hooks/useAuth.jsx';
import { createJob, pollJob, getResult } from '../api/jobs.js';

export default function TTS() {
  const { user } = useAuth();
  const { api } = useApi();
  const [text, setText] = useState('');
  const [selectedVoice, setSelectedVoice] = useState(null);
  const [voices, setVoices] = useState([]);
  const [pricing, setPricing] = useState({});
  const [isGenerating, setIsGenerating] = useState(false);
  const [audioUrl, setAudioUrl] = useState(null);
  const [result, setResult] = useState(null);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);

  // Giọng thật từ GET /v1/voices + bảng giá thật — trước đây gọi 405 nên grid
  // giọng trống trơn, và "Dùng tới ~N credits" là phép chia bịa.
  useEffect(() => {
    (async () => {
      try {
        const list = await api.get('/v1/voices');
        setVoices(list);
        if (list.length > 0) setSelectedVoice(list[0].id);
      } catch (e) {
        console.error('tải danh sách giọng thất bại', e);
      }
      try {
        setPricing(await api.get('/v1/pricing'));
      } catch (e) {
        console.error('tải bảng giá thất bại', e);
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
        setError(done.error || 'Tạo giọng nói thất bại (credit đã hoàn lại).');
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
    <div style={{ padding: '40px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '24px', fontWeight: 700 }}>
        TTS Studio
      </h1>
      <p style={{ color: 'var(--text-dim)', marginBottom: '48px' }}>
        Chuyển văn bản thành giọng nói tự nhiên với giọng đọc tiếng Việt của bạn
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '40px' }}>
        {/* Left: Editor & Controls */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          {/* Text input */}
          <div>
            <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '12px', fontWeight: 600 }}>
              Nhập văn bản
            </label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Xin chào, đây là VoiceVibe TTS Studio. Hãy nhập văn bản bạn muốn chuyển đổi thành giọng nói tại đây..."
              rows={12}
              style={{
                width: '100%',
                padding: '16px',
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
            <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '12px', fontWeight: 600 }}>
              Chọn giọng đọc
            </label>
            {voices.length === 0 ? (
              <div style={{ padding: '20px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
                Chưa có giọng nào — tạo giọng ở trang “Giọng Clone”, hoặc cứ tạo giọng nói với giọng mặc định của hệ thống.
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '16px' }}>
                {voices.map((v) => (
                  <button
                    key={v.id}
                    onClick={() => setSelectedVoice(v.id)}
                    style={{
                      background: selectedVoice === v.id ? 'var(--primary-light)' : 'var(--surface)',
                      border: selectedVoice === v.id ? '1px solid var(--primary)' : '1px solid var(--border)',
                      borderRadius: 'var(--radius)',
                      padding: '12px 16px',
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
              padding: '16px 32px',
              borderRadius: 'var(--radius)',
              fontSize: 'var(--text-base)',
              fontWeight: 600,
              cursor: text.trim() && !isGenerating ? 'pointer' : 'not-allowed',
              opacity: text.trim() && !isGenerating ? 1 : 0.6,
              maxWidth: '240px',
            }}
          >
            {isGenerating ? 'Đang tạo giọng nói...' : `Tạo giọng nói (${(Number(pricing.tts) || 10).toLocaleString('vi-VN')} credits)`}
          </button>

          {/* Error */}
          {error && (
            <div style={{
              padding: '16px', borderRadius: 'var(--radius)',
              background: 'var(--danger-light)', color: 'var(--danger)', whiteSpace: 'pre-wrap',
            }}>
              {error}
            </div>
          )}

          {/* Audio player */}
          {audioUrl && (
            <div>
              <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '12px', fontWeight: 600 }}>
                Kết quả
              </label>
              <audio
                controls
                src={audioUrl}
                style={{ width: '100%', outline: 'none' }}
              />
              <a href={result?.url} download={result?.filename} style={{ display: 'inline-block', marginTop: '12px', color: 'var(--primary)', fontWeight: 600 }}>
                Tải về máy ({result?.filename})
              </a>
            </div>
          )}

          {/* Status */}
          {job && job.status !== 'done' && !error && (
            <div style={{ padding: '16px', borderRadius: 'var(--radius)', background: 'var(--info-light)', color: 'var(--info)' }}>
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

        {/* Right sidebar: Credits and waveform placeholder */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          {/* Credits usage */}
          <div
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              padding: '24px',
            }}
          >
            <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: '16px', fontWeight: 700 }}>
              Credits
            </h3>
            <div style={{ fontSize: 'var(--text-base)', color: 'var(--text)', marginBottom: '8px' }}>
              Số dư: <span style={{ fontWeight: 600, color: 'var(--primary)' }}>{(user?.credits || 0).toLocaleString('vi-VN')}</span>
            </div>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
              Giá tạo giọng nói: {(Number(pricing.tts) || 10).toLocaleString('vi-VN')} credits/job (đọc từ server)
            </div>
          </div>

          {/* Waveform placeholder */}
          <div
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              padding: '24px',
              height: '200px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
              <div style={{ fontSize: '48px', marginBottom: '12px' }}>声波</div>
              <div style={{ fontSize: 'var(--text-sm)' }}>Waveform sẽ hiển thị tại đây sau khi tạo</div>
            </div>
          </div>

          {/* Tips */}
          <div
            style={{
              background: 'var(--info-light)',
              border: '1px solid var(--info)',
              borderRadius: 'var(--radius-lg)',
              padding: '16px',
            }}
          >
            <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '12px', color: 'var(--info)' }}>
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
