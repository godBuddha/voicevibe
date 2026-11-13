// B3+B4 + GE1 — trang "Xử lý video": in phụ đề song ngữ 2 style + CHỌN TỈ LỆ
// KHUNG (7 lựa chọn — hệ thống chỉ GỢI Ý theo video nguồn, người dùng tự
// chọn) + banner tiêu đề. 3 nhóm ĐỘC LẬP gộp MỘT job render. Phụ đề lấy từ
// file upload HOẶC job phụ đề/lồng tiếng đã chạy xong (không phải dịch lại).
import { useRef, useState } from 'react';
import { createJob, pollJob, getResult, uploadMedia } from '../api/jobs.js';

// Tỉ lệ khung — khớp ASPECT_TARGETS backend (render.py). mini = khung mini
// minh hoạ (px): dọc cao 26, ngang rộng 30, vuông 22, "original" nét đứt.
const ASPECTS = [
  { v: '9:16', name: '9:16', desc: 'Dọc — TikTok/Shorts/Reels' },
  { v: '4:5', name: '4:5', desc: 'Dọc — Feed' },
  { v: '1:1', name: '1:1', desc: 'Vuông' },
  { v: '4:3', name: '4:3', desc: 'Tỉ lệ cũ' },
  { v: '16:9', name: '16:9', desc: 'Ngang — YouTube' },
  { v: '21:9', name: '21:9', desc: 'Siêu rộng' },
  { v: 'original', name: 'Giữ nguyên', desc: 'Chỉ phụ đề/banner' },
];

// Gợi ý tỉ lệ theo khung nguồn — ngưỡng = trung điểm giữa các tỉ lệ kề
// (0.9 = giữa 4:5 và 1:1; 1.55 = giữa 4:3 và 16:9; 2.05 = giữa 16:9 và 21:9).
function suggestAspect(w, h) {
  const r = w / h;
  if (r < 0.7) return '9:16';
  if (r < 0.9) return '4:5';
  if (r < 1.15) return '1:1';
  if (r < 1.55) return '4:3';
  if (r < 2.05) return '16:9';
  return '21:9';
}

// Khung mini theo tỉ lệ (trừ "original" — nét đứt vì khung tuỳ nguồn).
function miniFrame(r) {
  if (r.v === 'original') {
    return { width: 26, height: 18, border: '1.5px dashed currentColor', borderRadius: 2 };
  }
  if (r.v === '1:1') return { width: 22, height: 22, border: '1.5px solid currentColor', borderRadius: 2 };
  if (r.v === '9:16' || r.v === '4:5') {
    const ratio = r.v === '9:16' ? 9 / 16 : 4 / 5;
    return { height: 26, width: Math.round(26 * ratio), border: '1.5px solid currentColor', borderRadius: 2 };
  }
  const ratio = r.v === '4:3' ? 4 / 3 : r.v === '16:9' ? 16 / 9 : 21 / 9;
  return { width: 30, height: Math.round(30 / ratio), border: '1.5px solid currentColor', borderRadius: 2 };
}

export default function Render() {
  const videoRef = useRef(null);
  const subRef = useRef(null);
  const [video, setVideo] = useState(null);
  const [subFile, setSubFile] = useState(null);
  const [subJobId, setSubJobId] = useState('');
  const [burn, setBurn] = useState(true);
  const [aspect, setAspect] = useState('9:16');
  const [suggested, setSuggested] = useState(null);
  const [srcDims, setSrcDims] = useState(null);
  const [bannerMajor, setBannerMajor] = useState('');
  const [bannerMinor, setBannerMinor] = useState('');
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  // Đọc khung nguồn ngay trên máy (không cần server): objectURL + metadata
  // → gợi ý tỉ lệ. Người dùng vẫn tự chọn — gợi ý chỉ là mặc định ban đầu.
  const probeVideo = (file) => {
    setVideo(file);
    setSuggested(null);
    setSrcDims(null);
    if (!file) return;
    const url = URL.createObjectURL(file);
    const el = document.createElement('video');
    el.preload = 'metadata';
    el.onloadedmetadata = () => {
      const w = el.videoWidth, h = el.videoHeight;
      if (w && h) {
        const sug = suggestAspect(w, h);
        setSrcDims([w, h]);
        setSuggested(sug);
        setAspect(sug); // gợi ý = mặc định ban đầu; bấm pill khác là đổi tự do
      }
      URL.revokeObjectURL(url);
    };
    el.onerror = () => URL.revokeObjectURL(url);
    el.src = url;
  };

  const doRender = async () => {
    setError(null);
    setResult(null);
    const hasFrame = aspect !== 'original';
    if (!video && !hasFrame && !bannerMajor && !bannerMinor) {
      setError('Cần chọn video và ít nhất một lựa chọn: in phụ đề / tỉ lệ khung khác "Giữ nguyên" / banner.');
      return;
    }
    try {
      let media_url = null;
      if (video) media_url = await uploadMedia(video);
      const payload = {
        type: 'render',
        aspect,
        burn_subtitles: burn,
        ...(bannerMajor || bannerMinor ? {
          banner: { major: bannerMajor, minor: bannerMinor },
        } : {}),
        ...(media_url ? { media_url } : {}),
      };
      if (burn) {
        if (subFile) {
          payload.subtitle_key = await uploadMedia(subFile);
        } else if (subJobId.trim()) {
          payload.subtitle_job_id = subJobId.trim();
        } else {
          setError('In phụ đề cần file phụ đề (.srt/.vtt/.ass) hoặc ID job phụ đề đã xong.');
          return;
        }
      }
      const created = await createJob(payload);
      const done = await pollJob(created.jobId, {
        onUpdate: setJob, timeoutMs: 45 * 60 * 1000,
      });
      if (done.status === 'failed') {
        setError(done.error || 'Xử lý video thất bại.');
      } else {
        setResult(await getResult(created.jobId));
      }
    } catch (e) {
      setError(e.message);
    }
  };

  const checkStyle = (checked) => ({
    display: 'flex', alignItems: 'center', gap: '8px',
    fontSize: 'var(--text-sm)', cursor: 'pointer',
  });
  const inputStyle = {
    padding: '8px 10px', borderRadius: 'var(--radius)',
    border: '1px solid var(--border)', background: 'var(--bg)',
    color: 'var(--text)', fontSize: 'var(--text-sm)',
  };

  return (
    <div style={{ padding: '20px', maxWidth: '1000px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '10px', fontWeight: 700 }}>
        Xử lý video
      </h1>
      <p style={{ color: 'var(--text-dim)', marginBottom: '18px' }}>
        Gộp 3 bước thành một: in phụ đề song ngữ 2 dòng (không chồng nhau),
        chọn tỉ lệ khung tuỳ ý (hệ gợi ý theo video nguồn), thêm banner tiêu
        đề. Bấm một lần ra video hoàn chỉnh.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: '20px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '10px', fontWeight: 600 }}>
              Video gốc (ngang hoặc dọc)
            </label>
            <input ref={videoRef} type="file" accept="video/*"
              onChange={(e) => probeVideo(e.target.files?.[0] || null)}
              style={{ fontSize: 'var(--text-sm)' }} />
            {video && (
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginTop: '4px' }}>
                {video.name} ({(video.size / 1024 / 1024).toFixed(1)} MB)
                {srcDims && ` — khung nguồn ${srcDims[0]}×${srcDims[1]}`}
              </div>
            )}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <label style={checkStyle(true)}>
              <input type="checkbox" checked={burn} onChange={(e) => setBurn(e.target.checked)} />
              <b>In phụ đề song ngữ 2 dòng</b> (bản gốc trên, bản dịch dưới)
            </label>
            {burn && (
              <div style={{ marginLeft: '24px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <input ref={subRef} type="file" accept=".srt,.vtt,.ass"
                  onChange={(e) => setSubFile(e.target.files?.[0] || null)}
                  style={{ fontSize: 'var(--text-xs)' }} />
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                  hoặc ID job phụ đề / lồng tiếng đã xong:
                </div>
                <input value={subJobId} onChange={(e) => setSubJobId(e.target.value)}
                  placeholder="Ví dụ: 8fa02c1a9b3d (xem ở trang Jobs)"
                  style={inputStyle} />
              </div>
            )}
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '10px', fontWeight: 600 }}>
              Tỉ lệ khung
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              {ASPECTS.map((a) => {
                const active = aspect === a.v;
                return (
                  <button key={a.v} type="button" onClick={() => setAspect(a.v)}
                    style={{
                      display: 'flex', flexDirection: 'column', alignItems: 'center',
                      gap: '4px', minWidth: '72px', cursor: 'pointer',
                      padding: '8px 10px', borderRadius: '16px',
                      background: active ? 'var(--primary-light)' : 'var(--surface)',
                      border: active ? '1.5px solid var(--primary)' : '1px solid var(--border)',
                      color: active ? 'var(--primary)' : 'var(--text-dim)',
                      fontWeight: active ? 600 : 400,
                    }}>
                    <span style={{
                      color: active ? 'var(--primary)' : 'var(--text-dim)',
                      display: 'block', lineHeight: 0,
                    }}>
                      <span style={{ display: 'inline-block', ...miniFrame(a) }} />
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: 'var(--text-sm)' }}>
                      {a.name}
                      {suggested === a.v && (
                        <span style={{
                          fontSize: 'var(--text-xs)', padding: '0 6px',
                          borderRadius: 'var(--radius-full)',
                          background: 'var(--accent-light)', color: 'var(--accent)',
                        }}>
                          Gợi ý
                        </span>
                      )}
                    </span>
                    <span style={{ fontSize: 'var(--text-xs)', opacity: 0.85 }}>{a.desc}</span>
                  </button>
                );
              })}
            </div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginTop: '8px' }}>
              {srcDims
                ? `Gợi ý theo video nguồn: ${srcDims[0]}×${srcDims[1]} → ${suggested}. Bạn có thể chọn tỉ lệ khác.`
                : 'Chọn video để hệ gợi ý tỉ lệ phù hợp — chọn xong vẫn đổi tự do.'}
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <input value={bannerMajor} onChange={(e) => setBannerMajor(e.target.value)}
              placeholder="Banner dòng chính (vàng lớn)" style={inputStyle} />
            <input value={bannerMinor} onChange={(e) => setBannerMinor(e.target.value)}
              placeholder="Banner dòng phụ (vàng nhỏ)" style={inputStyle} />
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
              Dải đen cao ≈20% khung, chữ co theo chiều cao khung — áp mọi tỉ lệ. Gõ gì hiện nấy.
            </div>
          </div>

          <button
            disabled={(!video && !subJobId && !subFile) || job?.status === 'running'}
            onClick={doRender}
            style={{
              background: 'var(--gradient)', color: '#fff', border: 'none',
              padding: '12px 16px', borderRadius: 'var(--radius)', fontWeight: 600,
              fontSize: 'var(--text-base)', cursor: 'pointer', maxWidth: '240px',
              opacity: (!video && !subJobId && !subFile) ? 0.6 : 1,
            }}
          >
            {job?.status === 'running' ? 'Đang xử lý…' : 'Bắt đầu xử lý'}
          </button>

          {error && (
            <div style={{
              padding: '12px', borderRadius: 'var(--radius)',
              background: 'var(--danger-light)', color: 'var(--danger)',
              whiteSpace: 'pre-wrap',
            }}>
              {error}
            </div>
          )}

          {result && (
            <div style={{
              padding: '12px', borderRadius: 'var(--radius)',
              background: 'var(--success-light)', color: 'var(--success)',
            }}>
              <div style={{ fontWeight: 600, marginBottom: '6px' }}>
                ✅ Xong — {result.filename}
              </div>
              <video controls src={result.url} style={{ width: '100%', borderRadius: 'var(--radius)' }} />
              <a href={result.url} download={result.filename}
                 style={{ display: 'inline-block', marginTop: '8px', color: 'var(--primary)', fontWeight: 600 }}>
                Tải về máy
              </a>
            </div>
          )}

          {job && job.status !== 'done' && !error && (
            <div style={{
              padding: '12px', borderRadius: 'var(--radius)',
              background: 'var(--info-light)', color: 'var(--info)',
            }}>
              <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '8px' }}>
                {job.progress?.message || 'Đang xử lý'} — {job.progress?.percent?.toFixed(1)}%
              </div>
              <div style={{
                height: '4px', borderRadius: '2px', background: 'var(--info)',
                width: `${job.progress?.percent ?? 0}%`, transition: 'width 0.6s',
              }} />
            </div>
          )}
        </div>

        <div>
          <div style={{
            background: 'var(--info-light)', border: '1px solid var(--info)',
            borderRadius: 'var(--radius-lg)', padding: '12px',
          }}>
            <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '10px', color: 'var(--info)' }}>
              💡 Mẹo
            </h4>
            <ul style={{ fontSize: 'var(--text-sm)', listStyle: 'none', padding: 0, margin: 0 }}>
              <li style={{ marginBottom: '8px' }}>• Dựng khung trước, in phụ đề sau — phụ đề đo bề rộng đúng khung đích</li>
              <li style={{ marginBottom: '8px' }}>• "Giữ nguyên" = không đổi khung, chỉ in phụ đề/banner trên video gốc</li>
              <li style={{ marginBottom: '8px' }}>• Khung siêu rộng (21:9) từ video dọc: video nhỏ giữa khung, không cắt mất nội dung — muốn cắt dùng Bàn điều khiển FFmpeg</li>
              <li>• Dùng ID job Lồng tiếng: video + phụ đề song ngữ trùng khớp giọng đã dub</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
