import { FolderOpen } from 'lucide-react';

export function RecentProjects({ jobs, navigate }) {
  const formatTime = (date) => {
    const isoDate = typeof date === 'string' ? new Date(date) : date;
    const seconds = Math.floor((Date.now() - isoDate.getTime()) / 1000);
    if (seconds < 60) return 'vừa xong';
    if (seconds < 3600) return `${Math.floor(seconds / 60)} phút`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} giờ`;
    return `${Math.floor(seconds / 86400)} ngày`;
  };

  const prettifyBytes = (bytes) => {
    if (!bytes) return '';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let size = bytes;
    while (size >= 1024 && i < units.length - 1) {
      size /= 1024;
      i++;
    }
    return `${size.toFixed(1)} ${units[i]}`;
  };

  const mapType = {
    dub: 'Dịch',
    tts: 'TTS',
    stt: 'STT',
    subtitle: 'Phụ đề',
  };

  const mapStatus = {
    done: { color: 'var(--success)', label: 'Hoàn thành' },
    completed: { color: 'var(--success)', label: 'Hoàn thành' },
    running: { color: 'var(--warning)', label: 'Đang chạy' },
    queued: { color: 'var(--text-dim)', label: 'Hàng đợi' },
    failed: { color: 'var(--danger)', label: 'Thất bại' },
  };

  if (!jobs || jobs.length === 0) {
    return (
      <div>
        <h3 style={{ fontSize: 'var(--text-base)', marginBottom: '10px', fontWeight: 700 }}>
          Dự án gần đây
        </h3>
        <div style={{ textAlign: 'center', padding: '24px', borderRadius: 'var(--radius)', background: 'var(--surface)', border: '1px solid var(--border)' }}>
          <FolderOpen size={28} style={{ color: 'var(--text-muted)', marginBottom: '8px' }} />
          <p style={{ color: 'var(--text-dim)', fontSize: 'var(--text-sm)', marginBottom: '0' }}>Chưa có dự án nào</p>
          <button
            onClick={() => navigate('/dub')}
            style={{
              background: 'var(--gradient)',
              color: '#fff',
              border: 'none',
              padding: '6px 14px',
              borderRadius: 'var(--radius-sm)',
              fontSize: 'var(--text-sm)',
              fontWeight: 600,
              cursor: 'pointer',
              marginTop: '12px',
            }}
          >
            Tạo dự án đầu tiên
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h3 style={{ fontSize: 'var(--text-base)', marginBottom: '10px', fontWeight: 700 }}>
        Dự án gần đây
      </h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: '8px' }}>
        {jobs.slice(0, 8).map((job) => (
          <button
            key={job.id}
            onClick={() => navigate('/jobs')}
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              padding: '10px 12px',
              textAlign: 'left',
              cursor: 'pointer',
              transition: 'all 0.15s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'translateY(-1px)';
              e.currentTarget.style.boxShadow = 'var(--shadow-sm)';
              e.currentTarget.style.borderColor = 'var(--border-strong)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'none';
              e.currentTarget.style.boxShadow = 'none';
              e.currentTarget.style.borderColor = 'var(--border)';
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
              <span style={{ fontSize: '10px', fontWeight: 600, padding: '1px 6px', borderRadius: 'var(--radius-xs)', background: 'var(--primary-light)', color: 'var(--primary)' }}>
                {mapType[job.type] || job.type}
              </span>
              <span
                style={{
                  fontSize: '10px',
                  fontWeight: 600,
                  padding: '1px 6px',
                  borderRadius: 'var(--radius-xs)',
                  backgroundColor: mapStatus[job.status]?.color || 'var(--text-dim)',
                  color: '#fff',
                }}
              >
                {mapStatus[job.status]?.label || job.status}
              </span>
            </div>
            {/* adaptJob đã tính sẵn nhãn hiển thị (tên file → đầu đoạn text →
                nhãn loại job) — đọc đúng field đó thay vì job.file/job.text
                vốn không bao giờ có ở SPA. */}
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: '4px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {job.label || job.type}
            </div>
            {/* Một số job (translate văn bản…) không có file/độ dài — chỉ vẽ
                dòng phụ khi CÓ dữ liệu, tránh dấu "|" trơ giữa khoảng trống. */}
            {(job.file?.size || job.file?.duration) && (
              <div style={{ fontSize: '10px', color: 'var(--text-dim)' }}>
                {[
                  job.file?.size && prettifyBytes(job.file.size),
                  job.file?.duration && `${Math.floor(job.file.duration / 60)}:${(job.file.duration % 60).toString().padStart(2, '0')}`,
                ].filter(Boolean).join(' | ')}
              </div>
            )}
            <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '4px' }}>
              {formatTime(job.createdAt)}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
