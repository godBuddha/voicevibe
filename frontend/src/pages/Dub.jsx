import { useState, useRef } from 'react';
import { useApi } from '../hooks/useApi.jsx';
import { useAuth } from '../hooks/useAuth.jsx';

const LANGUAGES = {
  vi: 'Tiếng Việt',
  en: 'Tiếng Anh',
  ja: 'Tiếng Nhật',
  zh: 'Tiếng Trung',
  fr: 'Tiếng Pháp',
  de: 'Tiếng Đức',
  es: 'Tiếng Tây Ban Nha',
  ko: 'Tiếng Hàn',
  ru: 'Tiếng Nga',
};

export default function Dub() {
  const { user } = useAuth();
  const { api } = useApi();
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [fromLang, setFromLang] = useState('en');
  const [toLang, setToLang] = useState('vi');
  const [voiceOption, setVoiceOption] = useState('original');
  const [demucsEnabled, setDemucsEnabled] = useState(false);
  const [customScript, setCustomScript] = useState('');
  const [estimate, setEstimate] = useState(null);
  const [job, setJob] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [dragActive, setDragActive] = useState(false);

  const handleFile = async (f) => {
    if (!f) return;
    if (f.type.startsWith('video/') || f.type.startsWith('audio/')) {
      setFile(f);
      calcEstimate(f);
    } else {
      alert('Chỉ hỗ trợ file video hoặc audio');
    }
  };

  const handleDrag = (e, entering) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(entering);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const calcEstimate = (f) => {
    const duration = 180; // Mock duration (seconds)
    const perMinute = 60;
    const minutes = Math.ceil(duration / perMinute);
    let credits = minutes * 50;
    if (demucsEnabled) credits += minutes * 20;
    if (customScript) credits += 10;
    setEstimate({ credits, duration, minutes });
  };

  const startDub = async () => {
    if (!file) return;
    setIsProcessing(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('fromLang', fromLang);
      formData.append('toLang', toLang);
      formData.append('voiceOption', voiceOption);
      formData.append('demucsEnabled', demucsEnabled);
      if (customScript) formData.append('customScript', customScript);
      formData.append('creditsEstimated', estimate.credits);

      const res = await api.post('/v1/jobs', { body: formData, isMultipart: true });
      setJob({ ...res, status: 'queued', progress: { percent: 0, step: 'Tải file', message: 'Đang tải file lên server...' } });
      pollJob(res.id);
    } catch (err) {
      alert('Lỗi khi tạo job: ' + err.message);
      setIsProcessing(false);
    }
  };

  const pollJob = async (jobId) => {
    const interval = setInterval(async () => {
      try {
        const j = await api.get(`/v1/jobs/${jobId}`);
        setJob(j);
        if (j.status === 'completed' || j.status === 'failed') {
          setIsProcessing(false);
          clearInterval(interval);
        }
      } catch {
        clearInterval(interval);
        setIsProcessing(false);
      }
    }, 2000);
  };

  const pipelineSteps = [
    { key: 'upload', label: 'Tải file' },
    { key: 'stt', label: 'Nhận dạng giọng nói (STT)' },
    { key: 'translate', label: 'Dịch thuật' },
    { key: 'tts', label: 'Tạo giọng nói mới (TTS)' },
    { key: 'mix', label: 'Trộn âm thanh' },
  ];

  return (
    <div style={{ padding: '40px', maxWidth: '1400px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '40px', fontWeight: 700 }}>
        Dịch Video & Audio
      </h1>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 400px', gap: '40px' }}>
        {/* Left: Form */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          {/* File upload */}
          <div>
            <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: '16px', fontWeight: 600 }}>Nguồn</h3>
            <div
              onDragEnter={(e) => handleDrag(e, true)}
              onDragLeave={(e) => handleDrag(e, false)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              style={{
                border: `2px dashed ${dragActive ? 'var(--primary)' : 'var(--border)'}`,
                borderRadius: 'var(--radius-lg)',
                padding: '48px',
                textAlign: 'center',
                cursor: 'pointer',
                background: dragActive ? 'var(--primary-light)' : 'var(--surface)',
                transition: 'all 0.3s',
              }}
            >
              <input
                type="file"
                ref={fileInputRef}
                onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                accept="video/*,audio/*"
                style={{ display: 'none' }}
              />
              <div style={{ fontSize: '48px', marginBottom: '16px' }}>📁</div>
              {file ? (
                <div>
                  <div style={{ fontWeight: 600, marginBottom: '8px' }}>{file.name}</div>
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                    {(file.size / 1024 / 1024).toFixed(2)} MB
                  </div>
                </div>
              ) : (
                <div>
                  <div style={{ fontWeight: 600, marginBottom: '8px' }}>Kéo và thả file video/audio vào đây</div>
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                    Hoặc nhấn để chọn file
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Languages */}
          <div>
            <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: '16px', fontWeight: 600 }}>Ngôn ngữ</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div>
                <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '8px' }}>
                  Ngôn ngữ gốc
                </label>
                <select
                  value={fromLang}
                  onChange={(e) => setFromLang(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    borderRadius: 'var(--radius)',
                    border: '1px solid var(--border)',
                    fontSize: 'var(--text-base)',
                    background: 'var(--bg)',
                    color: 'var(--text)',
                  }}
                >
                  {Object.entries(LANGUAGES).map(([code, name]) => (
                    <option key={code} value={code}>
                      {name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '8px' }}>
                  Ngôn ngữ đích
                </label>
                <select
                  value={toLang}
                  onChange={(e) => setToLang(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    borderRadius: 'var(--radius)',
                    border: '1px solid var(--border)',
                    fontSize: 'var(--text-base)',
                    background: 'var(--bg)',
                    color: 'var(--text)',
                  }}
                >
                  {Object.entries(LANGUAGES).map(([code, name]) => (
                    <option key={code} value={code}>
                      {name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Voice options */}
          <div>
            <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: '16px', fontWeight: 600 }}>Giọng nói</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {[
                { value: 'original', label: 'Giữ giọng gốc (thay thế speaker bằng AI)' },
                { value: 'clone', label: 'Giọng clone của tôi' },
                { value: 'ai', label: 'AI chọn giọng phù hợp' },
              ].map((opt) => (
                <label key={opt.value} style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name="voiceOption"
                    value={opt.value}
                    checked={voiceOption === opt.value}
                    onChange={(e) => setVoiceOption(e.target.value)}
                    style={{ margin: 0 }}
                  />
                  <span style={{ fontSize: 'var(--text-base)' }}>{opt.label}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Demucs toggle */}
          <div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={demucsEnabled}
                onChange={(e) => setDemucsEnabled(e.target.checked)}
                style={{ margin: 0 }}
              />
              <span style={{ fontSize: 'var(--text-base)' }}>
                Tách nhạc nền (Demucs) - giữ âm thanh gốc
              </span>
            </label>
          </div>

          {/* Custom script */}
          <div>
            <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '8px' }}>
              Kịch bản tùy chỉnh (tuỳ chọn)
            </label>
            <textarea
              placeholder="Dán kịch bản/rõi nội dung hữu ích để kết quả dịch chính xác..."
              value={customScript}
              onChange={(e) => setCustomScript(e.target.value)}
              rows={5}
              style={{
                width: '100%',
                padding: '10px 12px',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--border)',
                fontSize: 'var(--text-base)',
                background: 'var(--bg)',
                color: 'var(--text)',
                resize: 'vertical',
                fontFamily: 'inherit',
                lineHeight: 1.5,
              }}
            />
          </div>

          {/* Start button */}
          <button
            disabled={!file || isProcessing || (estimate && estimate.credits > (user?.credits || 0))}
            onClick={startDub}
            style={{
              background: 'var(--gradient)',
              color: '#fff',
              border: 'none',
              padding: '16px 32px',
              borderRadius: 'var(--radius)',
              fontSize: 'var(--text-base)',
              fontWeight: 600,
              cursor: file && !isProcessing ? 'pointer' : 'not-allowed',
              opacity: file && !isProcessing ? 1 : 0.6,
              maxWidth: '320px',
            }}
          >
            {estimate && estimate.credits > (user?.credits || 0)
              ? `Không đủ credits (cần ${estimate.credits.toLocaleString('vi-VN')})`
              : isProcessing
              ? 'Đang xử lý...'
              : estimate
              ? `Bắt đầu dịch (${estimate.credits.toLocaleString('vi-VN')} credits)`
              : 'Chọn file để tính credit'}
          </button>
        </div>

        {/* Right: Estimation & Pipeline */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          {/* Estimate */}
          {estimate && (
            <div
              style={{
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-lg)',
                padding: '24px',
              }}
            >
              <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: '20px', fontWeight: 600 }}>Ước tính</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-base)' }}>
                  <span style={{ color: 'var(--text-dim)' }}>Thời lượng</span>
                  <span style={{ fontWeight: 600 }}>{estimate.minutes} phút</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-base)' }}>
                  <span style={{ color: 'var(--text-dim)' }}>Credits</span>
                  <span style={{ fontWeight: 600, color: 'var(--primary)' }}>{estimate.credits.toLocaleString('vi-VN')}</span>
                </div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginTop: '12px' }}>
                  {demucsEnabled && '+ Demucs (tách nhạc nền) • '}
                  {customScript && '+ Kịch bản tùy chỉnh'}
                </div>
              </div>
            </div>
          )}

          {/* Pipeline */}
          <div
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              padding: '24px',
            }}
          >
            <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: '20px', fontWeight: 600 }}>Pipeline xử lý</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {pipelineSteps.map((step, i) => {
                const isDone = job && job.progress?.step === pipelineSteps[Math.min(job.progress?.stepIndex || 0, pipelineSteps.length - 1)]?.key;
                const isCurrent = job && job.progress?.step === step.key;
                return (
                  <div key={step.key} style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                    <div
                      style={{
                        width: '24px',
                        height: '24px',
                        borderRadius: 'var(--radius-full)',
                        background: isDone
                          ? 'var(--success)'
                          : isCurrent
                          ? 'var(--warning)'
                          : 'var(--text-muted)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: isDone || isCurrent ? '#fff' : 'var(--bg)',
                        fontSize: '12px',
                        fontWeight: 600,
                      }}
                    >
                      {isDone ? '✓' : i + 1}
                    </div>
                    <span style={{ fontSize: 'var(--text-sm)', color: isDone ? 'var(--success)' : isCurrent ? 'var(--text)' : 'var(--text-dim)', flex: 1 }}>
                      {step.label}
                    </span>
                  </div>
                );
              })}
              {job?.progress && (
                <div style={{ marginTop: '8px', fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                  {job.progress.message}
                </div>
              )}
              {job?.progress?.percent !== undefined && (
                <div style={{ marginTop: '8px' }}>
                  <div
                    style={{
                      height: '6px',
                      borderRadius: 'var(--radius-full)',
                      background: 'var(--border)',
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        height: '100%',
                        borderRadius: 'var(--radius-full)',
                        background: 'var(--primary)',
                        width: `${job.progress.percent}%`,
                        transition: 'width 0.6s',
                      }}
                    />
                  </div>
                  <div style={{ marginTop: '6px', fontSize: 'var(--text-xs)', color: 'var(--text-dim)', textAlign: 'center' }}>
                    {job.progress.percent.toFixed(1)}%
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}