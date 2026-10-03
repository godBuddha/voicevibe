import { useState, useRef, useEffect } from 'react';
import { useApi } from '../hooks/useApi.jsx';
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
  const { api } = useApi();
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [sourceUrl, setSourceUrl] = useState('');
  const [useYouTube, setUseYouTube] = useState(false);
  const [useCookies, setUseCookies] = useState(false); // GB8 — tải bằng cookies
  const [withSubs, setWithSubs] = useState(false);
  const [subSource, setSubSource] = useState('auto');
  const [fromLang, setFromLang] = useState('en');
  const [toLang, setToLang] = useState('vi');
  const [voiceOption, setVoiceOption] = useState('original');
  const [demucsEnabled, setDemucsEnabled] = useState(false);
  const [voices, setVoices] = useState([]);
  const [cloneVoiceId, setCloneVoiceId] = useState('');
  const [duration, setDuration] = useState(null);
  const [job, setJob] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [dragActive, setDragActive] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        setVoices(await api.get('/v1/voices'));
      } catch (e) {
        console.error('tải danh sách giọng thất bại', e);
      }
    })();
  }, [api]);

  const cloneVoice = voices.find((v) => String(v.id) === String(cloneVoiceId));

  const handleFile = async (f) => {
    if (!f) return;
    if (f.type.startsWith('video/') || f.type.startsWith('audio/')) {
      setFile(f);
      setDuration(null);
      setResult(null);
      setJob(null);
      setError(null);
      readDuration(f);
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

  // Thời lượng THẬT đọc từ metadata file (trước đây cứng 180 giây) — hiển thị
  // trên panel "Thông tin tệp", không gắn với bất kỳ con số tiền nào.
  const readDuration = async (f) => {
    const url = URL.createObjectURL(f);
    try {
      const d = await new Promise((resolve) => {
        const a = new Audio();
        a.onloadedmetadata = () => resolve(a.duration || 0);
        a.onerror = () => resolve(0);
        a.src = url;
      });
      setDuration(d);
    } finally {
      URL.revokeObjectURL(url);
    }
  };

  const startDub = async () => {
    if (!file && !sourceUrl.trim()) return;
    setIsProcessing(true);
    setError(null);
    setJob(null);
    setResult(null);
    try {
      // B1: dán link (yt-dlp tự tải) THAY cho upload file — file tải về có
      // tên cố định work/source.{ext}, backend đọc qua source_url.
      const payload = {
        type: 'dub',
        source_lang: fromLang,
        target_lang: toLang,
        // "Tách nhạc nền" = giữ âm thanh gốc nhỏ → source_low (Demucs); ngược
        // lại là im lặng tuyệt đối.
        background_mode: demucsEnabled ? 'source_low' : 'silence',
        // B4b: xuất thêm phụ đề song ngữ kèm video (Render dùng lại được)
        with_subs: withSubs,
        // B2: phụ đề YouTube sẵn có khi dán link — auto: lấy nếu có
        sub_source: sourceUrl.trim() ? subSource : 'whisper',
        // GB8: cookies chỉ khi job yêu cầu — mặc định tải ẩn danh
        use_cookies: useCookies,
      };
      if (sourceUrl.trim()) {
        payload.source_url = sourceUrl.trim();
      } else {
        // Chuẩn thật của backend: nộp file vào /v1/media/upload → media_key
        payload.media_url = await uploadMedia(file);
      }
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
        setError(done.error || 'Job thất bại.');
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
    <div style={{ padding: '20px', maxWidth: '1400px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '20px', fontWeight: 700 }}>
        Dịch Video & Audio
      </h1>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 400px', gap: '20px' }}>
        {/* Left: Form */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* File upload */}
          <div>
            <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: '12px', fontWeight: 600 }}>Nguồn</h3>
            <div
              onDragEnter={(e) => handleDrag(e, true)}
              onDragLeave={(e) => handleDrag(e, false)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              style={{
                border: `2px dashed ${dragActive ? 'var(--primary)' : 'var(--border)'}`,
                borderRadius: 'var(--radius-lg)',
                padding: '20px',
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
              <div style={{ fontSize: '48px', marginBottom: '12px' }}>📁</div>
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
            <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: '12px', fontWeight: 600 }}>Ngôn ngữ</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '8px' }}>
                  Ngôn ngữ gốc
                </label>
                <select
                  value={fromLang}
                  onChange={(e) => setFromLang(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 10px',
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
                    padding: '10px 10px',
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
            <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: '12px', fontWeight: 600 }}>Giọng nói</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {[
                { value: 'original', label: 'Giữ giọng gốc (thay thế speaker bằng AI)' },
                { value: 'clone', label: 'Giọng clone của tôi — mọi người nói dùng chung 1 giọng' },
                { value: 'ai', label: 'AI chọn giọng phù hợp' },
              ].map((opt) => (
                <label key={opt.value} style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
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
                    marginLeft: '14px',
                    maxWidth: '320px',
                    padding: '10px 10px',
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
                <div style={{ marginLeft: '14px', fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                  Chưa có giọng nào — tạo giọng ở trang “Giọng Clone” trước.
                </div>
              )}
            </div>
          </div>

          {/* B1 — dán link thay file upload (yt-dlp tự tải) */}
          <div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', marginBottom: '8px' }}>
              <input
                type="checkbox"
                checked={sourceUrl.trim() !== '' || useYouTube}
                onChange={(e) => {
                  setUseYouTube(e.target.checked);
                  if (e.target.checked) setFile(null);
                }}
                style={{ margin: 0 }}
              />
              <span style={{ fontSize: 'var(--text-base)', fontWeight: 600 }}>
                Dùng video từ link (YouTube…)
              </span>
            </label>
            {(sourceUrl.trim() !== '' || useYouTube) && (
              <>
                <input
                  value={sourceUrl}
                  onChange={(e) => setSourceUrl(e.target.value)}
                  placeholder="https://www.youtube.com/watch?v=…"
                  style={{
                    width: '100%', padding: '8px 10px', borderRadius: 'var(--radius)',
                    border: '1px solid var(--border)', background: 'var(--bg)',
                    color: 'var(--text)', fontSize: 'var(--text-sm)',
                  }}
                />
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', marginTop: '8px' }}>
                  <input
                    type="checkbox"
                    checked={withSubs}
                    onChange={(e) => setWithSubs(e.target.checked)}
                    style={{ margin: 0 }}
                  />
                  <span style={{ fontSize: 'var(--text-sm)' }}>
                    Xuất thêm phụ đề song ngữ kèm video (dùng cho Xử lý video)
                  </span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', marginTop: '6px' }}>
                  <input
                    type="checkbox"
                    checked={subSource !== 'whisper'}
                    onChange={(e) => setSubSource(e.target.checked ? 'auto' : 'whisper')}
                    style={{ margin: 0 }}
                  />
                  <span style={{ fontSize: 'var(--text-sm)' }}>
                    Dùng phụ đề YouTube sẵn có nếu video có (bỏ qua nghe lại — nhanh hơn nhiều)
                  </span>
                </label>
                {/* GB8 — công tắc cookies cạnh ô link */}
                <label
                  title="Tắt: tải ẩn danh (public video tải được, an toàn hơn). Bật: dùng cookies admin đặt ở Cài đặt — bắt buộc với video riêng tư / giới hạn tuổi."
                  style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', marginTop: '6px' }}
                >
                  <input
                    type="checkbox"
                    checked={useCookies}
                    onChange={(e) => setUseCookies(e.target.checked)}
                    style={{ margin: 0 }}
                  />
                  <span style={{ fontSize: 'var(--text-sm)' }}>
                    Tải bằng cookies đăng nhập (video riêng tư / giới hạn tuổi)
                  </span>
                </label>
              </>
            )}
          </div>

          {/* Demucs toggle */}
          <div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
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
              disabled={(!file && !sourceUrl.trim()) || isProcessing || (voiceOption === 'clone' && !cloneVoice)}
              onClick={startDub}
              style={{
                background: 'var(--gradient)',
                color: '#fff',
                border: 'none',
                padding: '12px 16px',
                borderRadius: 'var(--radius)',
                fontSize: 'var(--text-base)',
                fontWeight: 600,
                cursor: !file || isProcessing ? 'not-allowed' : 'pointer',
                opacity: !file || isProcessing || (voiceOption === 'clone' && !cloneVoice) ? 0.6 : 1,
                maxWidth: '320px',
              }}
            >
              {isProcessing ? 'Đang xử lý...' : file ? 'Bắt đầu dịch' : 'Chọn file để bắt đầu'}
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
              padding: '12px', borderRadius: 'var(--radius)',
              background: 'var(--danger-light)', color: 'var(--danger)', whiteSpace: 'pre-wrap',
            }}>
              {error}
            </div>
          )}

          {/* Result */}
          {result && (
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '14px' }}>
              <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: '12px', fontWeight: 600 }}>Kết quả lồng tiếng</h3>
              {result.kind === 'video' ? (
                <video controls src={result.url} style={{ width: '100%', borderRadius: 'var(--radius)' }} />
              ) : (
                <audio controls src={result.url} style={{ width: '100%' }} />
              )}
              <a href={result.url} download={result.filename} style={{ display: 'inline-block', marginTop: '10px', color: 'var(--primary)', fontWeight: 600 }}>
                Tải về máy ({result.filename})
              </a>
            </div>
          )}
        </div>

        {/* Right: Thông tin tệp & Pipeline */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Thời lượng đọc thật từ file — không có con số tiền nào */}
          {file && duration !== null && (
            <div
              style={{
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-lg)',
                padding: '14px',
              }}
            >
              <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: '12px', fontWeight: 600 }}>Thông tin tệp</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-base)' }}>
                  <span style={{ color: 'var(--text-dim)' }}>Thời lượng</span>
                  <span style={{ fontWeight: 600 }}>{fmtTime(duration)}</span>
                </div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginTop: '10px' }}>
                  {demucsEnabled && 'Đã bật tách nhạc nền (Demucs) • '}
                  Lồng tiếng chạy nhiều bước nên mất từ vài phút trở lên, tùy máy.
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
              padding: '14px',
            }}
          >
            <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: '12px', fontWeight: 600 }}>Pipeline xử lý</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {pipelineSteps.map((step, i) => {
                const isDone = currentStep > i;
                const isCurrent = currentStep === i;
                return (
                  <div key={step.key} style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
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
