import { useState } from 'react';
import { createJob, pollJob, getResult } from '../api/jobs.js';

// Bảng ngôn ngữ dùng chung kiểu hiển thị với các trang khác (Subtitle.jsx) —
// giữ nguyên một bộ để mọi dropdown trong app gọi tên giống nhau.
const LANGUAGES = {
  vi: 'Tiếng Việt', en: 'Tiếng Anh', ja: 'Tiếng Nhật', zh: 'Tiếng Trung',
  fr: 'Tiếng Pháp', de: 'Tiếng Đức', es: 'Tiếng Tây Ban Nha', ko: 'Tiếng Hàn',
  ru: 'Tiếng Nga',
};

export default function TranslateText() {
  const [text, setText] = useState('');
  const [sourceLang, setSourceLang] = useState('vi');
  const [targetLang, setTargetLang] = useState('en');
  const [job, setJob] = useState(null);
  const [translated, setTranslated] = useState(null);
  const [error, setError] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [copied, setCopied] = useState(false);

  const startTranslate = async () => {
    if (!text.trim()) {
      setError('Vui lòng nhập văn bản cần dịch');
      return;
    }
    setIsProcessing(true);
    setJob(null);
    setTranslated(null);
    setError(null);
    try {
      // Job thật: type=translate + text + cặp ngôn ngữ.
      const created = await createJob({
        type: 'translate',
        text,
        source_lang: sourceLang,
        target_lang: targetLang,
      });
      const done = await pollJob(created.jobId, { onUpdate: setJob });
      if (done.status === 'failed') {
        setError(done.error || 'Dịch thất bại.');
      } else {
        const res = await getResult(created.jobId);
        setTranslated(res.content ?? '');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsProcessing(false);
    }
  };

  const copyResult = async () => {
    await navigator.clipboard.writeText(translated || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const downloadTxt = () => {
    const blob = new Blob([translated || ''], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'ban-dich.txt';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div style={{ padding: '40px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '24px', fontWeight: 700 }}>
        Dịch văn bản
      </h1>
      <p style={{ color: 'var(--text-dim)', marginBottom: '48px' }}>
        Dịch văn bản giữa 9 ngôn ngữ bằng AI — dùng đúng bộ dịch đã cấu hình trong Model Hub, có chuỗi dự phòng về bộ dịch nhỏ chạy tại máy
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '40px' }}>
        {/* Left */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* Chọn cặp ngôn ngữ */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
              Dịch từ
              <select
                value={sourceLang}
                onChange={(e) => setSourceLang(e.target.value)}
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
            <span style={{ fontSize: '24px' }}>→</span>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
              Sang
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

          {/* Văn bản nguồn */}
          <div>
            <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '12px', fontWeight: 600 }}>
              Văn bản cần dịch
            </label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Nhập hoặc dán văn bản cần dịch vào đây..."
              rows={8}
              style={{
                width: '100%', padding: '16px',
                borderRadius: 'var(--radius-lg)', border: '1px solid var(--border)',
                fontSize: 'var(--text-base)', background: 'var(--bg)',
                color: 'var(--text)', resize: 'vertical', fontFamily: 'inherit',
                lineHeight: 1.6,
              }}
            />
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginTop: '8px', textAlign: 'right' }}>
              {text.length} ký tự
            </div>
          </div>

          {error && (
            <div style={{
              padding: '16px', borderRadius: 'var(--radius)',
              background: 'var(--danger-light)', color: 'var(--danger)', whiteSpace: 'pre-wrap',
            }}>
              {error}
            </div>
          )}

          <button
            disabled={isProcessing || !text.trim()}
            onClick={startTranslate}
            style={{
              background: 'var(--gradient)', color: '#fff', border: 'none',
              padding: '16px 32px', borderRadius: 'var(--radius)',
              fontSize: 'var(--text-base)', fontWeight: 600,
              cursor: isProcessing || !text.trim() ? 'not-allowed' : 'pointer',
              opacity: isProcessing || !text.trim() ? 0.6 : 1,
              maxWidth: '320px',
            }}
          >
            {isProcessing ? 'Đang dịch...' : 'Dịch ngay'}
          </button>

          {/* Progress */}
          {job && job.status !== 'done' && !error && (
            <div style={{ padding: '20px', borderRadius: 'var(--radius)', background: 'var(--info-light)', color: 'var(--info)' }}>
              <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                {job.status === 'queued' ? 'Hàng đợi' : job.status === 'running' ? 'Đang dịch' : job.status}
              </div>
            </div>
          )}

          {/* Kết quả */}
          {translated !== null && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h3 style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>
                  Bản dịch ({LANGUAGES[targetLang]})
                </h3>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    onClick={copyResult}
                    style={{
                      background: 'var(--info-light)', color: 'var(--info)', border: 'none',
                      padding: '8px 16px', borderRadius: 'var(--radius)',
                      fontSize: 'var(--text-sm)', fontWeight: 600, cursor: 'pointer',
                    }}
                  >
                    {copied ? 'Đã chép ✓' : 'Chép'}
                  </button>
                  <button
                    onClick={downloadTxt}
                    style={{
                      background: 'var(--success-light)', color: 'var(--success)', border: 'none',
                      padding: '8px 16px', borderRadius: 'var(--radius)',
                      fontSize: 'var(--text-sm)', fontWeight: 600, cursor: 'pointer',
                    }}
                  >
                    Tải .txt
                  </button>
                </div>
              </div>
              <div
                style={{
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-lg)', padding: '24px',
                  whiteSpace: 'pre-wrap', fontSize: 'var(--text-base)', lineHeight: 1.7,
                }}
              >
                {translated}
              </div>
            </div>
          )}
        </div>

        {/* Right sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          <div style={{ background: 'var(--info-light)', border: '1px solid var(--info)', borderRadius: 'var(--radius-lg)', padding: '20px' }}>
            <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '12px', color: 'var(--info)' }}>
              💡 Mẹo
            </h4>
            <ul style={{ fontSize: 'var(--text-sm)', color: 'var(--text)', listStyle: 'none', padding: 0, margin: 0 }}>
              <li style={{ marginBottom: '8px' }}>• Dán cả đoạn văn dài — AI dịch theo ngữ cảnh chứ không dịch từng từ</li>
              <li style={{ marginBottom: '8px' }}>• Muốn dịch lời thoại trong file audio/video? Dùng trang “Dịch âm thanh”</li>
              <li>• Bản dịch cũng nằm ở trang “Lịch sử Jobs” — tải lại được mọi lúc</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
