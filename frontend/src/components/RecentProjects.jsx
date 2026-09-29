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
        <h3 style={{ fontSize: 'var(--text-xl)', marginBottom: '24px', fontWeight: 700 }}>
          Dự án gần đây
        </h3>
        <div style={{ textAlign: 'center', padding: '48px', borderRadius: 'var(--radius)', background: 'var(--surface)', border: '1px solid var(--border)' }}>
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>📁</div>
          <p style={{ color: 'var(--text-dim)' }}>Chưa có dự án nào</p>
          <button
            onClick={() => navigate('/dub')}
            style={{
              background: 'var(--gradient)',
              color: '#fff',
              border: 'none',
              padding: '10px 20px',
              borderRadius: 'var(--radius)',
              fontWeight: 600,
              cursor: 'pointer',
              marginTop: '16px',
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
      <h3 style={{ fontSize: 'var(--text-xl)', marginBottom: '24px', fontWeight: 700 }}>
        Dự án gần đây
      </h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '16px' }}>
        {jobs.slice(0, 8).map((job) => (
          <button
            key={job.id}
            onClick={() => navigate('/jobs')}
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              padding: '16px',
              textAlign: 'left',
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              e.target.style.transform = 'translateY(-2px)';
              e.target.style.boxShadow = 'var(--shadow)';
            }}
            onMouseLeave={(e) => {
              e.target.style.transform = 'none';
              e.target.style.boxShadow = 'none';
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
              <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, padding: '2px 8px', borderRadius: 'var(--radius-xs)', background: 'var(--primary-light)', color: 'var(--primary)' }}>
                {mapType[job.type] || job.type}
              </span>
              <span
                style={{
                  fontSize: 'var(--text-xs)',
                  fontWeight: 600,
                  padding: '2px 8px',
                  borderRadius: 'var(--radius-xs)',
                  backgroundColor: mapStatus[job.status]?.color || 'var(--text-dim)',
                  color: '#fff',
                }}
              >
                {mapStatus[job.status]?.label || job.status}
              </span>
            </div>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '8px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {job.file?.name || job.text?.substring(0, 40)}
            </div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
              {job.file?.size && prettifyBytes(job.file.size)} | {job.file?.duration ? `${Math.floor(job.file.duration / 60)}:${(job.file.duration % 60).toString().padStart(2, '0')}` : ''}
            </div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginTop: '8px' }}>
              {formatTime(job.createdAt)}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}