import { useState, useRef } from 'react';
import { useApi } from '../hooks/useApi.jsx';
import { uploadMedia, createJob, pollJob, getResult, parseSrt } from '../api/jobs.js';

// Bảng ngôn ngữ — giữ một bộ giống Subtitle.jsx / TranslateText.jsx.
const LANGUAGES = {
  vi: 'Tiếng Việt', en: 'Tiếng Anh', ja: 'Tiếng Nhật', zh: 'Tiếng Trung',
  fr: 'Tiếng Pháp', de: 'Tiếng Đức', es: 'Tiếng Tây Ban Nha', ko: 'Tiếng Hàn',
  ru: 'Tiếng Nga',
};

export default function TranslateAudio() {
  const { api } = useApi();
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [sourceLang, setSourceLang] = useState('vi');
  const [targetLang, setTargetLang] = useState('en');
  const [stage, setStage] = useState(null); // 'stt' | 'translate'
  const [sttJob, setSttJob] = useState(null);
  const [trJob, setTrJob] = useState(null);
  const [transcript, setTranscript] = useState(null); // mảng cue từ SRT
  const [translated, setTranslated] = useState(null);
  const [error, setError] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const handleFile = (f) => {
    if (f && (f.type.startsWith('video/') || f.type.startsWith('audio/'))) {
      setFile(f);
      setTranscript(null);
      setTranslated(null);
      setSttJob(null);
      setTrJob(null);
      setError(null);
    } else {
      alert('Chỉ hỗ trợ file video hoặc audio');
    }
  };

  const startTranslate = async () => {
    if (!file) return;
    setIsProcessing(true);
    setError(null);
    setTranscript(null);
    setTranslated(null);
    try {
      // Hai giai đoạn dùng nguyên hai job có sẵn trong server — KHÔNG bịa
      // pipeline mới: (1) nghe ra chữ (type=stt, trả SRT), (2) dịch cả khối chữ
      // (type=translate). Cả hai job hiện đầy đủ trong Lịch sử Jobs.
      const media_url = await uploadMedia(file);

      setStage('stt');
      const sttPayload = { type: 'stt', media_url };
      if (sourceLang && sourceLang !== 'auto') sttPayload.source_lang = sourceLang;
      const sttCreated = await createJob(sttPayload);
      const sttDone = await pollJob(sttCreated.jobId, {
        onUpdate: setSttJob, timeoutMs: 30 * 60 * 1000,
      });
      if (sttDone.status === 'failed') {
        throw new Error(sttDone.error || 'Nghe ra chữ thất bại.');
      }
      const sttRes = await getResult(sttCreated.jobId);
      // to_srt (stt.py) gắn nhãn người nói ở CUỐI dòng: "text [SPEAKER_00]" —
      // parseSrt chỉ tách nhãn ở ĐẦU nên phải làm sạch ở đây, nếu không nhãn
      // "[SPEAKER_00]" lọt vào lời thoại hiển thị lẫn văn bản gửi đi dịch.
      const cues = parseSrt(sttRes.content || '').map((c) => {
        const m = c.text.match(/\[?(SPEAKER_\d+)\]?/);
        const text = c.text.replace(/\s*\[?SPEAKER_\d+\]?\s*/g, ' ').replace(/\s+/g, ' ').trim();
        return { ...c, text, speaker: m ? m[1] : c.speaker };
      });
      const plain = cues.map((c) => c.text).join('\n');
      if (!plain.trim()) {
        throw new Error('Không nghe được lời nào trong file — kiểm tra file có tiếng nói rõ ràng.');
      }
      setTranscript(cues);

      setStage('translate');
      const trCreated = await createJob({
        type: 'translate',
        text: plain,
        source_lang: sourceLang === 'auto' ? undefined : sourceLang,
        target_lang: targetLang,
      });
      const trDone = await pollJob(trCreated.jobId, {
        onUpdate: setTrJob, timeoutMs: 15 * 60 * 1000,
      });
      if (trDone.status === 'failed') {
        throw new Error(trDone.error || 'Dịch thất bại.');
      }
      const trRes = await getResult(trCreated.jobId);
      setTranslated(trRes.content ?? '');
    } catch (err) {
      setError(err.message);
    } finally {
      setIsProcessing(false);
      setStage(null);
    }
  };

  const downloadTxt = (content, name) => {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  };

  const baseName = file?.name?.replace(/\.[^.]+$/, '') || 'am-thanh';

  const stageLabel = {
    stt: 'Giai đoạn 1/2 — nghe ra chữ',
    translate: 'Giai đoạn 2/2 — dịch sang tiếng khác',
  };
  const activeJob = stage === 'stt' ? sttJob : trJob;

  return (
    <div style={{ padding: '40px', maxWidth: '1400px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '24px', fontWeight: 700 }}>
        Dịch âm thanh
      </h1>
      <p style={{ color: 'var(--text-dim)', marginBottom: '48px' }}>
        Nộp file audio/video → AI nghe ra lời thoại rồi dịch sang ngôn ngữ bạn chọn. Chạy 2 giai đoạn lần lượt: nghe ra chữ, rồi dịch
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '40px' }}>
        {/* Left */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          {/* Upload */}
          {!file && (
            <div
              onDragOver={(e) => e.preventDefault()}
              onDragEnter={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (e.dataTransfer.files?.[0]) handleFile(e.dataTransfer.files[0]);
              }}
              onClick={() => fileInputRef.current?.click()}
              style={{
                border: '2px dashed var(--border)', borderRadius: 'var(--radius-lg)',
                padding: '64px', textAlign: 'center', cursor: 'pointer',
                background: 'var(--surface)', minHeight: '240px',
                display: 'flex', flexDirection: 'column', alignItems: 'center',
                justifyContent: 'center', gap: '16px',
              }}
            >
              <input
                type="file" ref={fileInputRef} style={{ display: 'none' }}
                accept="video/*,audio/*"
                onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
              />
              <div style={{ fontSize: '64px' }}>🎧</div>
              <div>
                <div style={{ fontWeight: 600, marginBottom: '8px' }}>
                  Kéo và thả file audio/video vào đây
                </div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                  Hoặc nhấn để chọn file (MP3, WAV, MP4, MOV…)
                </div>
              </div>
            </div>
          )}

          {file && (
            <div style={{
              background: 'var(--surface)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)', padding: '16px 24px',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}>
              <div>
                <div style={{ fontWeight: 600 }}>{file.name}</div>
                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                  {(file.size / 1024 / 1024).toFixed(2)} MB
                </div>
              </div>
              <button
                onClick={() => { setFile(null); setError(null); }}
                style={{
                  background: 'var(--bg)', color: 'var(--text-dim)',
                  border: '1px solid var(--border)', padding: '6px 14px',
                  borderRadius: 'var(--radius)', fontSize: 'var(--text-sm)',
                  fontWeight: 600, cursor: 'pointer',
                }}
              >
                Đổi file
              </button>
            </div>
          )}

          {/* Cặp ngôn ngữ */}
          {file && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                Ngôn ngữ trong file
                <select
                  value={sourceLang}
                  onChange={(e) => setSourceLang(e.target.value)}
                  style={{
                    padding: '8px 12px', borderRadius: 'var(--radius)',
                    border: '1px solid var(--border)', fontSize: 'var(--text-sm)',
                    background: 'var(--bg)', color: 'var(--text)',
                  }}
                >
                  <option value="auto">Tự nhận diện</option>
                  {Object.entries(LANGUAGES).map(([code, name]) => (
                    <option key={code} value={code}>{name}</option>
                  ))}
                </select>
              </label>
              <span style={{ fontSize: '24px' }}>→</span>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                Dịch sang
                <select
                  value={targetLang}
                  onChange={(e) => setTargetLang(e.target.value)}
                  style={{
                    padding: '8px 12px', borderRadius: 'var(--radius)',
                    border: '1px solid var(--border)', fontSize: 'var(--text-sm)',
                    background: 'var(--bg)', color: 'var(--text)',
                  }}
                >
                  {Object.entries(LANGUAGES).map(([code, name]) => (
                    <option key={code} value={code}>{name}</option>
                  ))}
                </select>
              </label>
            </div>
          )}

          {error && (
            <div style={{
              padding: '16px', borderRadius: 'var(--radius)',
              background: 'var(--danger-light)', color: 'var(--danger)', whiteSpace: 'pre-wrap',
            }}>
              {error}
            </div>
          )}

          {file && !isProcessing && !translated && (
            <button
              onClick={startTranslate}
              style={{
                background: 'var(--gradient)', color: '#fff', border: 'none',
                padding: '16px 32px', borderRadius: 'var(--radius)',
                fontSize: 'var(--text-base)', fontWeight: 600, cursor: 'pointer',
                maxWidth: '360px',
              }}
            >
              Dịch âm thanh
            </button>
          )}

          {/* Progress 2 giai đoạn */}
          {isProcessing && (
            <div style={{ padding: '20px', borderRadius: 'var(--radius)', background: 'var(--info-light)', color: 'var(--info)' }}>
              <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '8px' }}>
                {stageLabel[stage] || 'Đang xử lý'}
              </div>
              {activeJob?.progress?.percent !== undefined && (
                <div>
                  <div style={{
                    height: '6px', borderRadius: '3px', background: 'var(--info)',
                    width: `${activeJob.progress.percent}%`, transition: 'width 0.6s',
                  }} />
                  <div style={{ fontSize: 'var(--text-xs)', marginTop: '8px' }}>
                    {activeJob.progress.percent.toFixed(1)}%
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Kết quả: lời thoại gốc + bản dịch */}
          {translated !== null && (
            <>
              {transcript?.length > 0 && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                    <h3 style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>
                      Lời thoại gốc ({transcript.length} câu)
                    </h3>
                    <button
                      onClick={() => downloadTxt(transcript.map((c) => c.text).join('\n'), `${baseName}-loi-thoai.txt`)}
                      style={{
                        background: 'var(--info-light)', color: 'var(--info)', border: 'none',
                        padding: '8px 16px', borderRadius: 'var(--radius)',
                        fontSize: 'var(--text-sm)', fontWeight: 600, cursor: 'pointer',
                      }}
                    >
                      Tải .txt
                    </button>
                  </div>
                  <div style={{
                    background: 'var(--surface)', border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-lg)', padding: '24px', maxHeight: '300px',
                    overflow: 'auto', whiteSpace: 'pre-wrap', fontSize: 'var(--text-base)',
                    lineHeight: 1.7,
                  }} className="scrollbar-thin">
                    {transcript.map((c, i) => (
                      <div key={i} style={{ marginBottom: '6px' }}>
                        {c.speaker && (
                          <span style={{ color: 'var(--text-dim)', fontSize: 'var(--text-xs)', marginRight: '8px' }}>
                            [{c.speaker}]
                          </span>
                        )}
                        {c.text}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <h3 style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>
                    Bản dịch ({LANGUAGES[targetLang]})
                  </h3>
                  <button
                    onClick={() => downloadTxt(translated, `${baseName}-ban-dich.txt`)}
                    style={{
                      background: 'var(--success-light)', color: 'var(--success)', border: 'none',
                      padding: '8px 16px', borderRadius: 'var(--radius)',
                      fontSize: 'var(--text-sm)', fontWeight: 600, cursor: 'pointer',
                    }}
                  >
                    Tải .txt
                  </button>
                </div>
                <div style={{
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-lg)', padding: '24px',
                  whiteSpace: 'pre-wrap', fontSize: 'var(--text-base)', lineHeight: 1.7,
                }}>
                  {translated}
                </div>
              </div>
              <button
                onClick={() => {
                  setFile(null);
                  setTranscript(null);
                  setTranslated(null);
                  setSttJob(null);
                  setTrJob(null);
                  setError(null);
                }}
                style={{
                  background: 'var(--bg)', color: 'var(--text-dim)',
                  border: '1px solid var(--border)', padding: '10px 20px',
                  borderRadius: 'var(--radius)', fontSize: 'var(--text-sm)',
                  fontWeight: 600, cursor: 'pointer', maxWidth: '200px',
                }}
              >
                Xử lý file khác
              </button>
            </>
          )}
        </div>

        {/* Right sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          <div style={{ background: 'var(--info-light)', border: '1px solid var(--info)', borderRadius: 'var(--radius-lg)', padding: '20px' }}>
            <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '12px', color: 'var(--info)' }}>
              💡 Mẹo
            </h4>
            <ul style={{ fontSize: 'var(--text-sm)', color: 'var(--text)', listStyle: 'none', padding: 0, margin: 0 }}>
              <li style={{ marginBottom: '8px' }}>• File nhiều người nói vẫn được — lời thoại gốc ghi kèm tên người nói</li>
              <li style={{ marginBottom: '8px' }}>• Hai job (nghe + dịch) hiện ở “Lịch sử Jobs” — tải lại transcript/bản dịch mọi lúc</li>
              <li>• Chỉ cần bản phụ đề có mốc giờ? Dùng trang “Dịch phụ đề”</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
