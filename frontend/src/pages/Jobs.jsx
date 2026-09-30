import { useState, useEffect, useRef } from 'react';
import { useApi } from '../hooks/useApi.jsx';
import { cancelJob, deleteJob, getResult } from '../api/jobs.js';
import { BASE } from '../api/client.js';

export default function Jobs() {
  const { api } = useApi();
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [result, setResult] = useState(null);
  const [resultError, setResultError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const resultCache = useRef({});
  const selectedIdRef = useRef(null);

  const fetchJobs = async () => {
    try {
      const data = await api.get('/v1/jobs');
      const items = data.items || [];
      setJobs(items);
      // Panel chi tiết theo kịp trạng thái mới (job đang chọn chạy tới done…).
      if (selectedIdRef.current) {
        const upd = items.find((x) => x.id === selectedIdRef.current);
        if (upd) setSelectedJob(upd);
      }
      return items;
    } catch (e) {
      console.error('tải danh sách job thất bại', e);
      return [];
    }
  };

  useEffect(() => {
    fetchJobs();
  }, [api]);

  // Tự refresh khi còn job đang chờ/chạy (trước đây phải bấm tay F5 mới thấy
  // tiến độ). Dừng khi không còn job nào đang hoạt động.
  const hasActive = jobs.some((j) => j.status === 'queued' || j.status === 'running');
  useEffect(() => {
    if (!hasActive) return undefined;
    const t = setInterval(fetchJobs, 5000);
    return () => clearInterval(t);
  }, [hasActive]);

  // Chọn job → nạp kết quả (đã cache). Effect cũng bắt được thời điểm job đang
  // chọn vừa chuyển sang `done` sau một lượt refresh.
  const selectJob = (job) => {
    setResult(null);
    setResultError(null);
    if (!job || selectedJob?.id === job.id) {
      selectedIdRef.current = null;
      setSelectedJob(null);
      return;
    }
    selectedIdRef.current = job.id;
    setSelectedJob(job);
  };

  useEffect(() => {
    if (!selectedJob || selectedJob.status !== 'done') return undefined;
    if (resultCache.current[selectedJob.id]) {
      setResult(resultCache.current[selectedJob.id]);
      return undefined;
    }
    let alive = true;
    getResult(selectedJob.id)
      .then((res) => {
        if (!alive) return;
        resultCache.current[selectedJob.id] = res;
        setResult(res);
      })
      .catch((e) => {
        if (alive) setResultError(e.message);
      });
    return () => { alive = false; };
  }, [selectedJob?.id, selectedJob?.status]);

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
    done: {
      color: 'var(--success)',
      bg: 'var(--success-light)',
      label: 'Hoàn thành',
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
    cancelled: {
      color: 'var(--text-muted)',
      bg: 'var(--bg)',
      label: 'Đã hủy',
    },
  };

  const mapType = {
    dub: { label: 'Lồng tiếng', icon: '🎬' },
    tts: { label: 'TTS', icon: '🗣️' },
    stt: { label: 'STT', icon: '🎙️' },
    subtitle: { label: 'Phụ đề', icon: '🎞️' },
    translate: { label: 'Dịch', icon: '🌐' },
  };

  // % hiển thị an toàn (trước đây toFixed trên giá trị lạ → NaN% trên UI).
  const fmtPercent = (p) => (Number.isFinite(Number(p)) ? Number(p).toFixed(1) : '0.0');

  // HỦY / XÓA. Hủy = job còn hoạt động (miễn phí — không trừ, không hoàn gì);
  // Xóa = job đã kết thúc (dọn khỏi lịch sử + file kết quả riêng). Hành động
  // trên hàng nào phải stopPropagation — hàng là vùng bấm chọn chi tiết.
  const [actionError, setActionError] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const doCancel = async (job, e) => {
    e.stopPropagation();
    if (!window.confirm('Hủy job này? Job đang chờ/xử lý sẽ bị dừng.')) return;
    setBusyId(job.id);
    setActionError(null);
    try {
      await cancelJob(job.id);
      await fetchJobs();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const doDelete = async (job, e) => {
    e.stopPropagation();
    if (!window.confirm('Xóa vĩnh viễn job này khỏi lịch sử? File kết quả riêng của job cũng bị dọn.')) return;
    setBusyId(job.id);
    setActionError(null);
    try {
      await deleteJob(job.id);
      if (selectedIdRef.current === job.id) {
        selectedIdRef.current = null;
        setSelectedJob(null);
      }
      delete resultCache.current[job.id];
      await fetchJobs();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const formatDate = (date) => {
    const d = date ? new Date(date) : null;
    if (!d || Number.isNaN(d.getTime())) return '—';
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
            <option value="done">Hoàn thành</option>
            <option value="failed">Thất bại</option>
            <option value="cancelled">Đã hủy</option>
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
            {Object.entries(mapType).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Results count */}
      <div style={{ marginBottom: '16px', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Hiển thị {filteredJobs.length} / {jobs.length} job</span>
        {actionError && <span style={{ color: 'var(--danger)', fontWeight: 600 }}>{actionError}</span>}
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
                const isActive = job.status === 'queued' || job.status === 'running';
                const isBusy = busyId === job.id;
                return (
                  <div
                    key={job.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => selectJob(job)}
                    onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && selectJob(job)}
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
                      e.currentTarget.style.transform = 'translateY(-2px)';
                      e.currentTarget.style.boxShadow = 'var(--shadow)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.transform = 'none';
                      if (selectedJob?.id !== job.id) e.currentTarget.style.boxShadow = 'none';
                    }}
                  >
                    <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
                      <div style={{ fontSize: '24px' }}>{type.icon}</div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px', gap: '8px' }}>
                          <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, padding: '2px 8px', borderRadius: 'var(--radius-xs)', background: status.bg, color: status.color, whiteSpace: 'nowrap' }}>
                            {status.label}
                          </span>
                        </div>
                        <div style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: '8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {job.label}
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                          <span>{type.label}</span>
                          <span>{formatDate(job.createdAt)}</span>
                        </div>
                        {isActive && job.progress?.percent !== undefined && (
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
                                  width: `${Number(job.progress.percent) || 0}%`,
                                  transition: 'width 0.6s',
                                }}
                              />
                            </div>
                            <div style={{ marginTop: '4px', fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                              {fmtPercent(job.progress.percent)}%
                            </div>
                          </div>
                        )}
                        {job.status === 'failed' && job.error && (
                          <div style={{ marginTop: '8px', fontSize: 'var(--text-xs)', color: 'var(--danger)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {job.error}
                          </div>
                        )}
                        {/* Hành động: Hủy (còn hoạt động) / Xóa (đã kết thúc).
                            Nút phải stopPropagation — hàng là vùng chọn chi tiết. */}
                        <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
                          {isActive && (
                            <button
                              disabled={isBusy}
                              onClick={(e) => doCancel(job, e)}
                              style={{
                                background: 'var(--warning-light)', color: 'var(--warning)',
                                border: 'none', padding: '6px 14px', borderRadius: 'var(--radius)',
                                fontSize: 'var(--text-xs)', fontWeight: 600,
                                cursor: isBusy ? 'wait' : 'pointer', opacity: isBusy ? 0.6 : 1,
                              }}
                            >
                              {isBusy ? 'Đang hủy...' : 'Hủy job'}
                            </button>
                          )}
                          {!isActive && (
                            <button
                              disabled={isBusy}
                              onClick={(e) => doDelete(job, e)}
                              style={{
                                background: 'var(--bg)', color: 'var(--danger)',
                                border: '1px solid var(--border)', padding: '6px 14px',
                                borderRadius: 'var(--radius)', fontSize: 'var(--text-xs)',
                                fontWeight: 600, cursor: isBusy ? 'wait' : 'pointer',
                                opacity: isBusy ? 0.6 : 1,
                              }}
                            >
                              {isBusy ? 'Đang xóa...' : 'Xóa'}
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
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
                    <span style={{ color: 'var(--text-dim)' }}>Đối tượng</span>
                    <span style={{ fontWeight: 600, maxWidth: '220px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={selectedJob.label}>
                      {selectedJob.label}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>Ngày tạo</span>
                    <span style={{ fontWeight: 600 }}>{formatDate(selectedJob.createdAt)}</span>
                  </div>
                  {selectedJob.status === 'done' && selectedJob.updatedAt && (                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'var(--text-dim)' }}>Hoàn thành</span>
                      <span style={{ fontWeight: 600 }}>{formatDate(selectedJob.updatedAt)}</span>
                    </div>
                  )}
                  {selectedJob.status === 'failed' && selectedJob.error && (
                    <div style={{ padding: '12px', borderRadius: 'var(--radius)', background: 'var(--danger-light)', color: 'var(--danger)', whiteSpace: 'pre-wrap' }}>
                      {selectedJob.error}
                    </div>
                  )}
                </div>
              </div>

              {/* Kết quả theo kind thật từ /v1/jobs/{id}/result */}
              {selectedJob.status === 'done' && result && (
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
                  {result.kind === 'audio' && (
                    <audio controls src={result.url} style={{ width: '100%' }} />
                  )}
                  {result.kind === 'video' && (
                    <video controls src={result.url} style={{ width: '100%', borderRadius: 'var(--radius)' }} />
                  )}
                  {result.kind === 'text' && (
                    <div
                      style={{
                        background: 'var(--bg)',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius)',
                        padding: '12px',
                        fontSize: 'var(--text-xs)',
                        whiteSpace: 'pre-wrap',
                        maxHeight: '200px',
                        overflow: 'auto',
                        fontFamily: 'monospace',
                      }}
                    >
                      {result.content || '(trống)'}
                    </div>
                  )}
                  <a
                    href={result.url || BASE + result.download_url}
                    download={result.filename}
                    style={{ display: 'inline-block', marginTop: '16px', color: 'var(--primary)', fontWeight: 600 }}
                  >
                    Tải về máy ({result.filename})
                  </a>
                </div>
              )}
              {selectedJob.status === 'done' && !result && resultError && (
                <div style={{ padding: '16px', borderRadius: 'var(--radius)', background: 'var(--danger-light)', color: 'var(--danger)' }}>
                  Không tải được kết quả: {resultError}
                </div>
              )}
              {selectedJob.status === 'done' && !result && !resultError && (
                <div style={{ padding: '16px', borderRadius: 'var(--radius)', background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
                  Đang tải kết quả...
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
