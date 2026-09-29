import { useState, useEffect } from 'react';
import { useApi } from '../hooks/useApi.jsx';

export default function Jobs() {
  const { api } = useApi();
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');

  useEffect(() => {
    fetchJobs();
  }, [api]);

  const fetchJobs = async () => {
    try {
      const data = await api.get('/v1/jobs');
      setJobs(data.items || []);
    } catch {}
  };

  const filteredJobs = jobs.filter((j) => {
    if (statusFilter !== 'all' && j.status !== statusFilter) return false;
    if (typeFilter !== 'all' && j.type !== typeFilter) return false;
    return true;
  });

  const mapStatus = {
    queued: {
      color: 'var(--text-muted)',
      bg: 'var(--bg)',
      label: 'Hàng đợi',
    },
    running: {
      color: 'var(--warning)',
      bg: 'var(--warning-light)',
      label: 'Đang chạy',
    },
    completed: {
      color: 'var(--success)',
      bg: 'var(--success-light)',
      label: 'Hoàn thành',
    },
    failed: {
      color: 'var(--danger)',
      bg: 'var(--danger-light)',
      label: 'Thất bại',
    },
  };

  const mapType = {
    dub: { label: 'Dịch', icon: '🎬' },
    tts: { label: 'TTS', icon: '🗣️' },
    stt: { label: 'STT', icon: '🎙️' },
    subtitle: { label: 'Phụ đề', icon: '🎞️' },
  };

  const formatDate = (date) => {
    const d = new Date(date);
    return d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div style={{ padding: '40px', maxWidth: '1400px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '24px', fontWeight: 700 }}>
        Lịch sử Jobs
      </h1>
      <p style={{ color: 'var(--text-dim)', marginBottom: '48px' }}>
        Theo dõi tất cả các job đã tạo và trạng thái xử lý
      </p>

      {/* Filters */}
      <div style={{ display: 'flex', gap: '16px', marginBottom: '32px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <label style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>Trạng thái:</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{
              padding: '8px 12px',
              borderRadius: 'var(--radius)',
              border: '1px solid var(--border)',
              fontSize: 'var(--text-sm)',
              background: 'var(--bg)',
              color: 'var(--text)',
            }}
          >
            <option value="all">Tất cả</option>
            <option value="queued">Hàng đợi</option>
            <option value="running">Đang chạy</option>
            <option value="completed">Hoàn thành</option>
            <option value="failed">Thất bại</option>
          </select>
        </div>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <label style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>Loại:</label>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            style={{
              padding: '8px 12px',
              borderRadius: 'var(--radius)',
              border: '1px solid var(--border)',
              fontSize: 'var(--text-sm)',
              background: 'var(--bg)',
              color: 'var(--text)',
            }}
          >
            <option value="all">Tất cả</option>
            <option value="dub">Dịch</option>
            <option value="tts">TTS</option>
            <option value="stt">STT</option>
            <option value="subtitle">Phụ đề</option>
          </select>
        </div>
      </div>

      {/* Results count */}
      <div style={{ marginBottom: '16px', fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
        Hiển thị {filteredJobs.length} / {jobs.length} job
      </div>

      {/* Job list */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: '32px' }}>
        <div>
          {filteredJobs.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '64px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)' }}>
              <div style={{ fontSize: '48px', marginBottom: '16px' }}>📋</div>
              <div style={{ color: 'var(--text-dim)' }}>Không có job nào</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {filteredJobs.map(job => {
                const status = mapStatus[job.status] || { color: 'var(--text-dim)', bg: 'var(--bg)', label: job.status };
                const type = mapType[job.type] || { label: job.type, icon: '📄' };
                return (
                  <button
                    key={job.id}
                    onClick={() => setSelectedJob(selectedJob?.id === job.id ? null : job)}
                    style={{
                      background: selectedJob?.id === job.id ? 'var(--primary-light)' : 'var(--surface)',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius-lg)',
                      padding: '20px',
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
                      if (selectedJob?.id !== job.id) e.target.style.boxShadow = 'none';
                    }}
                  >
                    <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
                      <div style={{ fontSize: '24px' }}>{type.icon}</div>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                          <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, padding: '2px 8px', borderRadius: 'var(--radius-xs)', background: status.bg, color: status.color }}>
                            {status.label}
                          </span>
                          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                            #{job.id}
                          </span>
                        </div>
                        <div style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: '8px' }}>
                          {job.file?.name || (job.text?.substring(0, 60) + (job.text?.length > 60 ? '...' : ''))}
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                          <span>{type.label}</span>
                          <span>{formatDate(job.createdAt)}</span>
                        </div>
                        {job.progress?.percent !== undefined && (
                          <div style={{ marginTop: '8px' }}>
                            <div
                              style={{
                                height: '4px',
                                borderRadius: '2px',
                                background: 'var(--border)',
                                overflow: 'hidden',
                              }}
                            >
                              <div
                                style={{
                                  height: '100%',
                                  borderRadius: '2px',
                                  background: 'var(--primary)',
                                  width: `${job.progress.percent}%`,
                                  transition: 'width 0.6s',
                                }}
                              />
                            </div>
                            <div style={{ marginTop: '4px', fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                              {job.progress.percent.toFixed(1)}% • {job.progress?.message}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Job details */}
        <div>
          {selectedJob ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
              <div
                style={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-lg)',
                  padding: '24px',
                }}
              >
                <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, marginBottom: '20px' }}>
                  Chi tiết Job #{selectedJob.id}
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: 'var(--text-sm)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Loại</span>
                    <span style={{ fontWeight: 600 }}>{mapType[selectedJob.type]?.label || selectedJob.type}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Trạng thái</span>
                    <span style={{ color: mapStatus[selectedJob.status]?.color || 'var(--text-dim)', fontWeight: 600 }}>
                      {mapStatus[selectedJob.status]?.label || selectedJob.status}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>File</span>
                    <span style={{ fontWeight: 600 }}>{selectedJob.file?.name || 'N/A'}</span>
                  </div>
                  {selectedJob.file?.size && (
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'var(--text-dim)' }}>Kích thước</span>
                      <span style={{ fontWeight: 600 }}>{(selectedJob.file.size / 1024 / 1024).toFixed(2)} MB</span>
                    </div>
                  )}
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Ngày tạo</span>
                    <span style={{ fontWeight: 600 }}>{formatDate(selectedJob.createdAt)}</span>
                  </div>
                  {selectedJob.completedAt && (
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'var(--text-dim)' }}>Hoàn thành</span>
                      <span style={{ fontWeight: 600 }}>{formatDate(selectedJob.completedAt)}</span>
                    </div>
                  )}
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Credits</span>
                    <span style={{ fontWeight: 600 }}>{selectedJob.creditsUsed || 0}</span>
                  </div>
                </div>
              </div>

              {selectedJob.result && (
                <div
                  style={{
                    background: 'var(--surface)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-lg)',
                    padding: '24px',
                  }}
                >
                  <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, marginBottom: '20px' }}>
                    Kết quả
                  </h3>
                  {selectedJob.result.url && (
                    <div style={{ marginBottom: '16px' }}>
                      <audio controls src={selectedJob.result.url} style={{ width: '100%' }} />
                    </div>
                  )}
                  {selectedJob.result.transcript && (
                    <div
                      style={{
                        background: 'var(--bg)',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius)',
                        padding: '12px',
                        fontSize: 'var(--text-sm)',
                        whiteSpace: 'pre-wrap',
                        maxHeight: '200px',
                        overflow: 'auto',
                      }}
                    >
                      {selectedJob.result.transcript}
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '40px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)' }}>
              <div style={{ fontSize: '48px', marginBottom: '16px' }}>📄</div>
              <div style={{ color: 'var(--text-dim)' }}>Chọn một job để xem chi tiết</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}