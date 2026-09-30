import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Mic, Sparkles } from 'lucide-react';
import { useApi } from '../hooks/useApi.jsx';
import { QuickTools } from '../components/QuickTools.jsx';
import { DonutChart } from '../components/DonutChart.jsx';
import { StatsCards } from '../components/StatsCards.jsx';
import { RecentProjects } from '../components/RecentProjects.jsx';
import { FeatureCards } from '../components/FeatureCards.jsx';

export default function Dashboard() {
  const [usage, setUsage] = useState(null);
  const [jobs, setJobs] = useState([]);
  const { api } = useApi();
  const navigate = useNavigate();

  useEffect(() => {
    (async () => {
      try {
        const usageData = await api.get('/v1/usage');
        setUsage(usageData);
        const jobsData = await api.get('/v1/jobs');
        setJobs(jobsData.items);
      } catch {}
    })();
  }, [api]);

  return (
    <div style={{ padding: '16px 20px 24px', maxWidth: '1400px' }}>
      {/* COMPACT UI: banner hero dày 48px padding thành một thanh mảnh một hàng —
          tiêu đề + mô tả gộp bên trái, 2 nút hành động bên phải. Không còn khối
          gradient cao ~220px chiếm trọn màn hình đầu tiên. */}
      <div
        style={{
          background: 'var(--gradient)',
          borderRadius: 'var(--radius-lg)',
          padding: '12px 16px',
          color: '#fff',
          marginBottom: '14px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '12px',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, lineHeight: 1.3 }}>
            Dịch Audio, Video Online — Xoá nhòa cách biệt ngôn ngữ
          </div>
          <div style={{ fontSize: 'var(--text-sm)', opacity: 0.85, marginTop: '2px' }}>
            Chuyển đổi văn bản và giọng nói giữa 44+ ngôn ngữ với AI tiên tiến nhất
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
          <button
            onClick={() => navigate('/dub')}
            style={{
              background: '#fff',
              color: 'var(--primary)',
              padding: '6px 12px',
              borderRadius: 'var(--radius-sm)',
              border: 'none',
              fontSize: 'var(--text-sm)',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <Sparkles size={13} /> Bắt đầu ngay
          </button>
          <button
            onClick={() => navigate('/tts')}
            style={{
              background: 'rgba(255,255,255,0.18)',
              color: '#fff',
              padding: '6px 12px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid rgba(255,255,255,0.35)',
              fontSize: 'var(--text-sm)',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <Mic size={13} /> Tạo giọng nói
          </button>
        </div>
      </div>

      {/* Stats */}
      <StatsCards usage={usage} />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: '14px', marginTop: '14px' }}>
        {/* Main content */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', minWidth: 0 }}>
          <FeatureCards />
          <QuickTools navigate={navigate} />
          <RecentProjects jobs={jobs} navigate={navigate} />
        </div>

        {/* Right sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {/* Usage donut — đếm theo JOB (self-host miễn phí, không có đơn vị tiền) */}
          <div
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              padding: '14px',
            }}
          >
            <h3 style={{ fontSize: 'var(--text-base)', marginBottom: '10px', fontWeight: 700 }}>
              Job theo loại
            </h3>
            <DonutChart usage={usage} />
          </div>
        </div>
      </div>
    </div>
  );
}
