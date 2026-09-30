import { useEffect, useRef } from 'react';

export function DonutChart({ usage }) {
  const canvasRef = useRef(null);
  // Đếm JOB theo loại (self-host miễn phí — không có đơn vị tiền tệ).
  const total = usage?.totalJobs || 0;

  const breakdown = usage?.breakdown || {};
  // Đủ màu cho MỌI loại job (trước đây thiếu stt/dub/subtitle → vẽ không màu
  // + chấm màu undefined ở chú giải).
  const colors = {
    tts: '#7c3aed',
    translate: '#ec4899',
    video: '#10b981',
    stt: '#3b82f6',
    dub: '#8b5cf6',
    subtitle: '#14b8a6',
    other: '#f59e0b',
  };
  const labels = {
    tts: 'TTS',
    translate: 'Dịch thuật',
    video: 'Video AI',
    stt: 'STT',
    dub: 'Lồng tiếng',
    subtitle: 'Phụ đề',
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    const centerX = w / 2;
    const centerY = h / 2;
    const radius = Math.min(centerX, centerY) - 14;
    const lineWidth = 22;

    ctx.clearRect(0, 0, w, h);

    // Background circle
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.strokeStyle = 'var(--border)';
    ctx.lineWidth = lineWidth;
    ctx.stroke();

    // Draw segments — mỗi loại chiếm phần của TỔNG job
    let currentAngle = -Math.PI / 2;
    for (const key of Object.keys(breakdown)) {
      const val = breakdown[key] || 0;
      if (val === 0 || total === 0) continue;
      const segAngle = (val / total) * Math.PI * 2;
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, currentAngle, currentAngle + segAngle);
      ctx.strokeStyle = colors[key];
      ctx.lineWidth = lineWidth;
      ctx.stroke();
      currentAngle += segAngle;
    }

    // Center text — tổng số job
    ctx.fillStyle = 'var(--text)';
    ctx.font = 'bold 19px Inter';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(`${total.toLocaleString('vi-VN')}`, centerX, centerY - 8);
    ctx.font = '11px Inter';
    ctx.fillStyle = 'var(--text-dim)';
    ctx.fillText('Jobs', centerX, centerY + 13);
  }, [usage, colors, total]);

  if (!usage) return null;

  return (
    <div style={{ textAlign: 'center' }}>
      <canvas
        ref={canvasRef}
        width={160}
        height={160}
        style={{ maxWidth: '160px', maxHeight: '160px' }}
      />
      <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '5px', textAlign: 'left' }}>
        {Object.entries(breakdown).map(([key, val]) => (
          <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div
              style={{
                width: '9px',
                height: '9px',
                borderRadius: '2px',
                backgroundColor: colors[key] || '#94a3b8',
              }}
            />
            <div style={{ flex: 1, fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
              {labels[key] || 'Khác'}
            </div>
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text)' }}>
              {val.toLocaleString('vi-VN')}
            </div>
          </div>
        ))}
        {total === 0 && (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
            Chưa có job nào — tạo job đầu tiên từ menu bên trái.
          </div>
        )}
      </div>
    </div>
  );
}
