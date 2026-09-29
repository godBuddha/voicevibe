import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
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
    <div style={{ padding: '32px 40px', maxWidth: '1400px' }}>
      {/* Hero */}
      <div
        style={{
          background: 'var(--gradient)',
          borderRadius: 'var(--radius-xl)',
          padding: '48px',
          color: '#fff',
          marginBottom: '48px',
        }}
      >
        <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '16px', fontWeight: 800 }}>
          Dịch Audio, Video Online / Xoá nhòa cách biệt ngôn ngữ
        </h1>
        <p style={{ fontSize: 'var(--text-lg)', opacity: 0.9, marginBottom: '32px', maxWidth: '600px' }}>
          Chuyển đổi văn bản và giọng nói giữa 44+ ngôn ngữ với AI tiên tiến nhất
        </p>
        <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
          <button
            onClick={() => navigate('/dub')}
            style={{
              background: '#fff',
              color: 'var(--primary)',
              padding: '14px 24px',
              borderRadius: 'var(--radius)',
              border: 'none',
              fontSize: 'var(--text-base)',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Bắt đầu ngay
          </button>
          <button
            onClick={() => navigate('/pricing')}
            style={{
              background: 'rgba(255,255,255,0.2)',
              color: '#fff',
              padding: '14px 24px',
              borderRadius: 'var(--radius)',
              border: '1px solid rgba(255,255,255,0.3)',
              fontSize: 'var(--text-base)',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Xem gói dịch vụ
          </button>
        </div>
      </div>

      {/* Stats */}
      <StatsCards usage={usage} />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '32px', marginTop: '48px' }}>
        {/* Main content */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '48px' }}>
          <FeatureCards />
          <QuickTools navigate={navigate} />
          <RecentProjects jobs={jobs} navigate={navigate} />
        </div>

        {/* Right sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          {/* Usage donut */}
          <div
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              padding: '24px',
            }}
          >
            <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: '20px', fontWeight: 700 }}>
              Mức sử dụng của bạn
            </h3>
            <DonutChart usage={usage} />
          </div>

          {/* Upgrade card */}
          <div
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              padding: '24px',
              marginTop: '24px',
            }}
          >
            <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: '12px', fontWeight: 700 }}>
              Nâng cấp gói Yêu Thương
            </h3>
            <p style={{ color: 'var(--text-dim)', fontSize: 'var(--text-sm)', marginBottom: '20px' }}>
              Nhận đến 2 triệu credits mỗi tháng và các tính năng ưu tiên
            </p>
            <button
              onClick={() => navigate('/pricing')}
              style={{
                background: 'var(--gradient)',
                color: '#fff',
                border: 'none',
                width: '100%',
                padding: '12px 20px',
                borderRadius: 'var(--radius)',
                fontWeight: 600,
                cursor: 'pointer',
                fontSize: 'var(--text-base)',
              }}
            >
              Xem gói nâng cấp
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}