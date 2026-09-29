import { useState, useRef, useEffect } from 'react';
import { useApi } from '../hooks/useApi.jsx';
import { useAuth } from '../hooks/useAuth.jsx';

export default function TTS() {
  const { user } = useAuth();
  const { api } = useApi();
  const audioRef = useRef(null);
  const [text, setText] = useState('');
  const [selectedVoice, setSelectedVoice] = useState(1);
  const [voices, setVoices] = useState([]);
  const [speed, setSpeed] = useState(1.0);
  const [pitch, setPitch] = useState(0);
  const [isGenerating, setIsGenerating] = useState(false);
  const [audioUrl, setAudioUrl] = useState(null);
  const [job, setJob] = useState(null);
  const [credits, setCredits] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await api.get('/v1/voices');
        setVoices(data);
        if (data.length > 0) setSelectedVoice(data[0].id);
      } catch {}
    })();
  }, [api]);

  const generateSpeech = async () => {
    if (!text.trim()) {
      alert('Vui lòng nhập văn bản để tạo giọng nói');
      return;
    }
    setIsGenerating(true);
    setAudioUrl(null);
    try {
      const body = {
        text,
        voiceId: selectedVoice,
        speed,
        pitch,
        creditsEstimated: Math.ceil(text.length / 10),
      };
      const res = await api.post('/v1/jobs', { body });
      setJob({ ...res, status: 'queued', progress: { percent: 0, step: 'TTS', message: 'Đang tạo giọng nói...' } });
      pollJob(res.id);
    } catch (err) {
      alert('Lỗi khi tạo giọng nói: ' + err.message);
      setIsGenerating(false);
    }
  };

  const pollJob = async (jobId) => {
    const interval = setInterval(async () => {
      try {
        const j = await api.get(`/v1/jobs/${jobId}`);
        setJob(j);
        if (j.status === 'completed') {
          setIsGenerating(false);
          if (j.result?.url) {
            setAudioUrl(j.result.url);
          }
          clearInterval(interval);
        } else if (j.status === 'failed') {
          setIsGenerating(false);
          alert('Tạo giọng nói thất bại');
          clearInterval(interval);
        }
      } catch {
        clearInterval(interval);
        setIsGenerating(false);
      }
    }, 2000);
  };

  const previewVoice = async (voice) => {
    if (audioRef.current) {
      try {
        audioRef.current.volume = 0.8;
        audioRef.current.play();
        setTimeout(() => {
          if (audioRef.current) audioRef.current.pause();
          audioRef.current.currentTime = 0;
        }, 4000);
      } catch {}
    }
  };

  const formattedSpeed = speed.toFixed(1);
  const formattedPitch = pitch > 0 ? `+${pitch}` : pitch.toString();

  return (
    <div style={{ padding: '40px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '24px', fontWeight: 700 }}>
        TTS Studio
      </h1>
      <p style={{ color: 'var(--text-dim)', marginBottom: '48px' }}>
        Chuyển văn bản thành giọng nói tự nhiên với hơn 10 giọng đọc tiếng Việt
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
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '16px' }}>
              {voices.map((v) => (
                <button
                  key={v.id}
                  onClick={() => setSelectedVoice(v.id)}
                  style={{
                    background: selectedVoice === v.id ? 'var(--primary-light)' : 'var(--surface)',
                    border: '1px solid var(--border)',
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
                  <div style={{ fontSize: '20px' }}>{v.gender === 'female' ? '👩' : '👨'}</div>
                  <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                    {v.name}
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      previewVoice(v);
                    }}
                    style={{
                      fontSize: '12px',
                      padding: '4px 8px',
                      borderRadius: '4px',
                      background: 'var(--info-light)',
                      color: 'var(--info)',
                      border: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    🎧 Nghe thử
                  </button>
                </button>
              ))}
            </div>
          </div>

          {/* Voice settings */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px' }}>
            <div>
              <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '12px', fontWeight: 600 }}>
                Tốc độ: {formattedSpeed}x
              </label>
              <input
                type="range"
                min={0.5}
                max={2.0}
                step={0.1}
                value={speed}
                onChange={(e) => setSpeed(parseFloat(e.target.value))}
                style={{ width: '100%' }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginTop: '4px' }}>
                <span>0.5x</span>
                <span>2.0x</span>
              </div>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '12px', fontWeight: 600 }}>
                Cao độ: {formattedPitch}
              </label>
              <input
                type="range"
                min={-10}
                max={10}
                step={1}
                value={pitch}
                onChange={(e) => setPitch(parseInt(e.target.value))}
                style={{ width: '100%' }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginTop: '4px' }}>
                <span>-10</span>
                <span>+10</span>
              </div>
            </div>
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
            {isGenerating ? 'Đang tạo giọng nói...' : 'Tạo giọng nói'}
          </button>

          {/* Audio player */}
          {audioUrl && (
            <div>
              <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '12px', fontWeight: 600 }}>
                Kết quả
              </label>
              <audio
                ref={audioRef}
                controls
                src={audioUrl}
                style={{ width: '100%', outline: 'none' }}
              />
            </div>
          )}

          {/* Status */}
          {job && job.status !== 'completed' && (
            <div style={{ padding: '16px', borderRadius: 'var(--radius)', background: 'var(--info-light)', color: 'var(--info)' }}>
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
              Dùng tới:~{Math.ceil(text.length / 10)} credits
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
              <li style={{ marginBottom: '8px' }}>• Tăng/giảm tốc độ để học ngoại ngữ</li>
              <li>• Nghe thử giọng đọc trước khi tạo file</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}