// B3+B4 — trang "Xử lý video": in phụ đề song ngữ 2 style + cắt dọc 9:16 +
// banner tiêu đề. 3 bật/tắt gộp MỘT job render — bấm 1 lần ra video TikTok/
// Shorts hoàn chỉnh. Phụ đề lấy từ file upload HOẶC job phụ đề/lồng tiếng
// đã chạy xong (không phải dịch lại).
import { useRef, useState } from 'react';
import { createJob, pollJob, getResult, uploadMedia } from '../api/jobs.js';

export default function Render() {
  const videoRef = useRef(null);
  const subRef = useRef(null);
  const [video, setVideo] = useState(null);
  const [subFile, setSubFile] = useState(null);
  const [subJobId, setSubJobId] = useState('');
  const [burn, setBurn] = useState(true);
  const [vertical, setVertical] = useState(true);
  const [bannerMajor, setBannerMajor] = useState('');
  const [bannerMinor, setBannerMinor] = useState('');
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const doRender = async () => {
    setError(null);
    setResult(null);
    if (!video && !vertical && !bannerMajor && !bannerMinor) {
      setError('Cần chọn video và ít nhất một lựa chọn.');
      return;
    }
    try {
      let media_url = null;
      if (video) media_url = await uploadMedia(video);
      const payload = {
        type: 'render',
        burn_subtitles: burn,
        vertical,
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

  return (
    <div style={{ padding: '20px', maxWidth: '1000px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '10px', fontWeight: 700 }}>
        Xử lý video
      </h1>
      <p style={{ color: 'var(--text-dim)', marginBottom: '18px' }}>
        Gộp 3 bước thành một: in phụ đề song ngữ 2 dòng (không chồng nhau),
        cắt khung dọc 9:16 cho TikTok/Shorts, thêm banner tiêu đề. Bấm một lần
        ra video hoàn chỉnh.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: '20px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '10px', fontWeight: 600 }}>
              Video gốc (ngang hoặc dọc)
            </label>
            <input ref={videoRef} type="file" accept="video/*"
              onChange={(e) => setVideo(e.target.files?.[0] || null)}
              style={{ fontSize: 'var(--text-sm)' }} />
            {video && (
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginTop: '4px' }}>
                {video.name} ({(video.size / 1024 / 1024).toFixed(1)} MB)
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
                  style={{
                    padding: '8px 10px', borderRadius: 'var(--radius)',
                    border: '1px solid var(--border)', background: 'var(--bg)',
                    color: 'var(--text)', fontSize: 'var(--text-sm)',
                  }} />
              </div>
            )}
            <label style={checkStyle(true)}>
              <input type="checkbox" checked={vertical} onChange={(e) => setVertical(e.target.checked)} />
              <b>Cắt dọc 9:16</b> (720×1280 — TikTok / Shorts / Reels)
            </label>
            <div style={{ marginLeft: '24px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <input value={bannerMajor} onChange={(e) => setBannerMajor(e.target.value)}
                placeholder="Banner dòng chính (vàng lớn)"
                style={{
                  padding: '8px 10px', borderRadius: 'var(--radius)',
                  border: '1px solid var(--border)', background: 'var(--bg)',
                  color: 'var(--text)', fontSize: 'var(--text-sm)',
                }} />
              <input value={bannerMinor} onChange={(e) => setBannerMinor(e.target.value)}
                placeholder="Banner dòng phụ (vàng nhỏ)"
                style={{
                  padding: '8px 10px', borderRadius: 'var(--radius)',
                  border: '1px solid var(--border)', background: 'var(--bg)',
                  color: 'var(--text)', fontSize: 'var(--text-sm)',
                }} />
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                Dải đen cao 250px phía trên — gõ gì hiện nấy, không cần đúng cú pháp.
              </div>
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
              <li style={{ marginBottom: '8px' }}>• Cắt dọc trước, in phụ đề sau — phụ đề đo bề rộng đúng khung dọc</li>
              <li style={{ marginBottom: '8px' }}>• Dùng ID job Lồng tiếng: video + phụ đề song ngữ trùng khớp giọng đã dub</li>
              <li>• Bật cả 3 → 1 lần encode duy nhất, nhanh hơn chạy riêng từng cái</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
