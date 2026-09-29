import { useState, useRef, useEffect } from 'react';
import { useApi } from '../hooks/useApi.jsx';
import { useAuth } from '../hooks/useAuth.jsx';
import { uploadMedia, createJob, pollJob, getResult } from '../api/jobs.js';

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

const fmtTime = (s) => {
  if (!Number.isFinite(s) || s <= 0) return '--:--';
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return `${m}:${String(sec).padStart(2, '0')}`;
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
  const [voices, setVoices] = useState([]);
  const [cloneVoiceId, setCloneVoiceId] = useState('');
  const [pricing, setPricing] = useState({});
  const [estimate, setEstimate] = useState(null);
  const [job, setJob] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [dragActive, setDragActive] = useState(false);

  // Giọng clone + bảng giá thật: trước đây chưa từng tải cả hai (voices gọi
  // 405, pricing không ai gọi) — ước tính credit là số bịa 50/phút.
  useEffect(() => {
    (async () => {
      try {
        setVoices(await api.get('/v1/voices'));
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

  // Bảng giá về sau khi người dùng đã chọn file (mạng chậm) → tính lại ước
  // tính, không để "0 credits" đứng đời (đã gặp thật qua tunnel).
  useEffect(() => {
    if (file && estimate && !estimate.credits) calcEstimate(file);
  }, [pricing]); // eslint-disable-line react-hooks/exhaustive-deps

  const cloneVoice = voices.find((v) => String(v.id) === String(cloneVoiceId));

  const handleFile = async (f) => {
    if (!f) return;
    if (f.type.startsWith('video/') || f.type.startsWith('audio/')) {
      setFile(f);
      setEstimate(null);
      setResult(null);
      setJob(null);
      setError(null);
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

  // Ước tính THẬT: thời lượng đọc từ metadata file (trước đây cứng 180 giây)
  // và credit là GIÁ PHẲNG mỗi job theo bảng giá backend — server không thu
  // theo phút (đã gặp thật: con số ước tính luôn sai với mọi file).
  const calcEstimate = async (f) => {
    const url = URL.createObjectURL(f);
    try {
      const duration = await new Promise((resolve) => {
        const a = new Audio();
        a.onloadedmetadata = () => resolve(a.duration || 0);
        a.onerror = () => resolve(0);
        a.src = url;
      });
      setEstimate({ credits: Number(pricing.dub) || 0, duration });
    } finally {
      URL.revokeObjectURL(url);
    }
  };

  const startDub = async () => {
    if (!file) return;
    setIsProcessing(true);
    setError(null);
    setJob(null);
    setResult(null);
    try {
      // Chuẩn thật của backend: nộp file vào /v1/media/upload → nhận media_key,
      // rồi tạo job JSON có `type`. (Trước đây nộp thẳng multipart không `type`
      // → 422, nút bấm thành cờ mờ.)
      const media_url = await uploadMedia(file);
      const payload = {
        type: 'dub',
        media_url,
        source_lang: fromLang,
        target_lang: toLang,
        // "Tách nhạc nền" = giữ âm thanh gốc nhỏ → source_low (Demucs); ngược
        // lại là im lặng tuyệt đối.
        background_mode: demucsEnabled ? 'source_low' : 'silence',
      };
      // Chọn giọng riêng → map MỌI người nói về một giọng ("*" = áp cho tất cả;
      // UI không biết trước id speaker vì diarization chạy sau khi job bắt đầu).
      if (voiceOption === 'clone' && cloneVoice) {
        payload.speaker_voices = { '*': cloneVoice.name };
      }
      const created = await createJob(payload);
      // Lồng tiếng CPU chạy nhiều phút — hẹn giờ rộng, không bỏ giữa chừng.
      const done = await pollJob(created.jobId, {
        onUpdate: setJob,
        timeoutMs: 45 * 60 * 1000,
      });
      if (done.status === 'failed') {
        setError(done.error || 'Job thất bại (credit đã hoàn lại).');
      } else {
        setResult(await getResult(created.jobId));
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsProcessing(false);
    }
  };

  // Pipeline card hiển thị bước hiện tại theo % thật của job (trước đây đọc
  // job.progress.step — field không tồn tại, bảng bước đứng yên vĩnh viễn).
  const stepFromPercent = (p) => (p >= 80 ? 4 : p >= 50 ? 3 : p >= 30 ? 2 : p >= 10 ? 1 : 0);
  const currentStep = job && Number.isFinite(job.progress?.percent) ? stepFromPercent(job.progress.percent) : -1;

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
                { value: 'clone', label: 'Giọng clone của tôi — mọi người nói dùng chung 1 giọng' },
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
              {voiceOption === 'clone' && (
                <select
                  value={cloneVoiceId}
                  onChange={(e) => setCloneVoiceId(e.target.value)}
                  style={{
                    marginLeft: '28px',
                    maxWidth: '320px',
                    padding: '10px 12px',
                    borderRadius: 'var(--radius)',
                    border: '1px solid var(--border)',
                    fontSize: 'var(--text-base)',
                    background: 'var(--bg)',
                    color: 'var(--text)',
                  }}
                >
                  <option value="">— chọn giọng của bạn —</option>
                  {voices.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.name} ({v.lang})
                    </option>
                  ))}
                </select>
              )}
              {voiceOption === 'clone' && !voices.length && (
                <div style={{ marginLeft: '28px', fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                  Chưa có giọng nào — tạo giọng ở trang “Giọng Clone” trước.
                </div>
              )}
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

          {/* Start button */}
          <div>
            <button
              disabled={
                !file || isProcessing || (voiceOption === 'clone' && !cloneVoice) ||
                (estimate && estimate.credits > (user?.credits || 0))
              }
              onClick={startDub}
              style={{
                background: 'var(--gradient)',
                color: '#fff',
                border: 'none',
                padding: '16px 32px',
                borderRadius: 'var(--radius)',
                fontSize: 'var(--text-base)',
                fontWeight: 600,
                cursor: !file || isProcessing ? 'not-allowed' : 'pointer',
                opacity: !file || isProcessing || (voiceOption === 'clone' && !cloneVoice) ? 0.6 : 1,
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
            {voiceOption === 'clone' && !cloneVoice && (
              <div style={{ marginTop: '8px', fontSize: 'var(--text-sm)', color: 'var(--warning)' }}>
                Hãy chọn một giọng trước khi bắt đầu.
              </div>
            )}
          </div>

          {/* Error */}
          {error && (
            <div style={{
              padding: '16px', borderRadius: 'var(--radius)',
              background: 'var(--danger-light)', color: 'var(--danger)', whiteSpace: 'pre-wrap',
            }}>
              {error}
            </div>
          )}

          {/* Result */}
          {result && (
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '24px' }}>
              <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: '16px', fontWeight: 600 }}>Kết quả lồng tiếng</h3>
              {result.kind === 'video' ? (
                <video controls src={result.url} style={{ width: '100%', borderRadius: 'var(--radius)' }} />
              ) : (
                <audio controls src={result.url} style={{ width: '100%' }} />
              )}
              <a href={result.url} download={result.filename} style={{ display: 'inline-block', marginTop: '12px', color: 'var(--primary)', fontWeight: 600 }}>
                Tải về máy ({result.filename})
              </a>
            </div>
          )}
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
                  <span style={{ fontWeight: 600 }}>{fmtTime(estimate.duration)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-base)' }}>
                  <span style={{ color: 'var(--text-dim)' }}>Credits</span>
                  <span style={{ fontWeight: 600, color: 'var(--primary)' }}>
                    {estimate.credits.toLocaleString('vi-VN')} (giá phẳng mỗi job)
                  </span>
                </div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginTop: '12px' }}>
                  {demucsEnabled && '+ Demucs (tách nhạc nền) • '}
                  Giá theo bảng giá hệ thống, đọc từ server
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
                const isDone = currentStep > i;
                const isCurrent = currentStep === i;
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
