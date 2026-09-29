import { useEffect, useRef } from 'react';

export function DonutChart({ usage }) {
  const canvasRef = useRef(null);
  const total = usage?.limit || 100;
  const used = usage?.used || 0;
  const percent = total > 0 ? (used / total) * 100 : 0;

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

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    const centerX = w / 2;
    const centerY = h / 2;
    const radius = Math.min(centerX, centerY) - 20;
    const lineWidth = 30;

    ctx.clearRect(0, 0, w, h);

    // Background circle
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.strokeStyle = 'var(--border)';
    ctx.lineWidth = lineWidth;
    ctx.stroke();

    // Draw segments
    let currentAngle = -Math.PI / 2;
    for (const key of Object.keys(breakdown)) {
      const val = breakdown[key] || 0;
      if (val === 0) continue;
      const segAngle = (val / used) * (Math.PI * 2 * (used / total));
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, currentAngle, currentAngle + segAngle);
      ctx.strokeStyle = colors[key];
      ctx.lineWidth = lineWidth;
      ctx.stroke();
      currentAngle += segAngle;
    }

    // Center text
    ctx.fillStyle = 'var(--text)';
    ctx.font = 'bold 24px Inter';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(`${percent.toFixed(1)}%`, centerX, centerY - 10);
    ctx.font = '14px Inter';
    ctx.fillStyle = 'var(--text-dim)';
    ctx.fillText('Đã sử dụng', centerX, centerY + 16);
  }, [usage, colors, used, total]);

  if (!usage) return null;

  return (
    <div style={{ textAlign: 'center' }}>
      <canvas
        ref={canvasRef}
        width={200}
        height={200}
        style={{ maxWidth: '200px', maxHeight: '200px' }}
      />
      <div style={{ marginTop: '20px', display: 'flex', flexDirection: 'column', gap: '12px', textAlign: 'left' }}>
        {Object.entries(breakdown).map(([key, val]) => (
          <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: '12px',
                height: '12px',
                borderRadius: '2px',
                backgroundColor: colors[key] || '#94a3b8',
              }}
            />
            <div style={{ flex: 1, fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
              { {tts: 'TTS', translate: 'Dịch thuật', video: 'Video AI', stt: 'STT', dub: 'Lồng tiếng', subtitle: 'Phụ đề'}[key] || 'Khác' }
            </div>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text)' }}>
              {val.toLocaleString('vi-VN')}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}