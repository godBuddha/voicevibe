import { useState, useRef, useEffect } from 'react';
import { useApi } from '../hooks/useApi.jsx';

export default function Subtitle() {
  const { api } = useApi();
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [cues, setCues] = useState([]);
  const [job, setJob] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [exportFormat, setExportFormat] = useState('srt');
  const [isBilingual, setIsBilingual] = useState(false);
  const [editingIndex, setEditingIndex] = useState(null);
  const [editText, setEditText] = useState('');
  const [timeRange, setTimeRange] = useState({ start: '', end: '' });

  const handleFile = (f) => {
    if (f && f.type.startsWith('video/')) {
      setFile(f);
      setCues([]);
      setJob(null);
    } else {
      alert('Chỉ hỗ trợ file video');
    }
  };

  const startSubtitle = async () => {
    if (!file) return;
    setIsProcessing(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('isBilingual', isBilingual);
      const res = await api.post('/v1/jobs', { body: formData, isMultipart: true });
      setJob({ ...res, status: 'queued', progress: { percent: 0, step: 'Tạo phụ đề', message: 'Đang xử lý video...' } });
      pollJob(res.id);
    } catch (err) {
      alert('Lỗi khi tạo phụ đề: ' + err.message);
      setIsProcessing(false);
    }
  };

  const pollJob = async (jobId) => {
    const interval = setInterval(async () => {
      try {
        const j = await api.get(`/v1/jobs/${jobId}`);
        setJob(j);
        if (j.status === 'completed') {
          setIsProcessing(false);
          if (j.result?.cues) setCues(j.result.cues);
          clearInterval(interval);
        } else if (j.status === 'failed') {
          setIsProcessing(false);
          alert('Tạo phụ đề thất bại');
          clearInterval(interval);
        }
      } catch {
        clearInterval(interval);
        setIsProcessing(false);
      }
    }, 2000);
  };

  const prettifyTime = (seconds) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 1000);
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')},${ms.toString().padStart(3, '0')}`;
  };

  const startEdit = (index) => {
    setEditingIndex(index);
    setEditText(cues[index].text);
    setTimeRange({
      start: prettifyTime(cues[index].start),
      end: prettifyTime(cues[index].end),
    });
  };

  const saveEdit = () => {
    const start = parseTime(timeRange.start);
    const end = parseTime(timeRange.end);
    if (!isNaN(start) && !isNaN(end) && start < end) {
      setCues([...cues.slice(0, editingIndex), { ...cues[editingIndex], start, end, text: editText }, ...cues.slice(editingIndex + 1)]);
      setEditingIndex(null);
      setEditText('');
      setTimeRange({ start: '', end: '' });
    } else {
      alert('Thời gian không hợp lệ');
    }
  };

  const parseTime = (str) => {
    const parts = str.split(/[:,]/).map(Number);
    if (parts.length === 4) return parts[0] * 3600 + parts[1] * 60 + parts[2] + parts[3] / 1000;
    if (parts.length === 3) return parts[0] * 60 + parts[1] + parts[2] / 1000;
    if (parts.length === 2) return parts[0] + parts[1] / 1000;
    return NaN;
  };

  const exportSubtitle = () => {
    let content = '';
    const name = file?.name?.replace(/\.[^.]+$/, '') || 'subtitle';
    if (exportFormat === 'srt') {
      content = cues.map((c, i) => `${i + 1}\n${prettifyTime(c.start)} --> ${prettifyTime(c.end)}\n${c.text}\n`).join('\n');
    } else if (exportFormat === 'vtt') {
      content = 'WEBVTT\n\n' + cues.map(c => `${prettifyTime(c.start)} --> ${prettifyTime(c.end)}\n${c.text}`).join('\n\n');
    } else if (exportFormat === 'ass') {
      content = '[Script Info]\nTitle: ' + name + '\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,16,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,2,10,10,10,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,' + cues.map(c => `${c.start},${c.end},Default,,0,0,0,,${c.text.replace('\n', '\\N')}`).join('\nDialogue: 0,');
    }

    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${name}.${exportFormat}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div style={{ padding: '40px', maxWidth: '1400px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '24px', fontWeight: 700 }}>
        Tạo phụ đề tự động
      </h1>
      <p style={{ color: 'var(--text-dim)', marginBottom: '48px' }}>
        Tạo phụ đề SRT, VTT, ASS từ video với công nghệ AI tiên tiến
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '40px' }}>
        {/* Left */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          {/* Upload */}
          {!cues.length && !job && (
            <div
              onDragOver={(e) => e.preventDefault()}
              onDragEnter={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (e.dataTransfer.files?.[0]) handleFile(e.dataTransfer.files[0]);
              }}
              onClick={() => fileInputRef.current?.click()}
              style={{
                border: '2px dashed var(--border)',
                borderRadius: 'var(--radius-lg)',
                padding: '64px',
                textAlign: 'center',
                cursor: 'pointer',
                background: 'var(--surface)',
                minHeight: '280px',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '16px',
              }}
            >
              <input
                type="file"
                ref={fileInputRef}
                onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                accept="video/*"
                style={{ display: 'none' }}
              />
              <div style={{ fontSize: '64px' }}>🎬</div>
              {file ? (
                <div>
                  <div style={{ fontWeight: 600, marginBottom: '8px' }}>{file.name}</div>
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                    {(file.size / 1024 / 1024).toFixed(2)} MB
                  </div>
                </div>
              ) : (
                <div>
                  <div style={{ fontWeight: 600, marginBottom: '8px' }}>Kéo và thả file video vào đây</div>
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                    Hoặc nhấn để chọn file (MP4, MOV, AVI, MKV)
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Options */}
          {!cues.length && file && (
            <>
              <div>
                <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={isBilingual}
                    onChange={(e) => setIsBilingual(e.target.checked)}
                    style={{ margin: 0 }}
                  />
                  <span style={{ fontSize: 'var(--text-base)' }}>Phụ đề song ngữ (nguồn + dịch)</span>
                </label>
              </div>
              <button
                disabled={isProcessing}
                onClick={startSubtitle}
                style={{
                  background: 'var(--gradient)',
                  color: '#fff',
                  border: 'none',
                  padding: '16px 32px',
                  borderRadius: 'var(--radius)',
                  fontSize: 'var(--text-base)',
                  fontWeight: 600,
                  cursor: isProcessing ? 'not-allowed' : 'pointer',
                  opacity: isProcessing ? 0.6 : 1,
                  maxWidth: '320px',
                }}
              >
                {isProcessing ? 'Đang tạo phụ đề...' : 'Tạo phụ đề'}
              </button>
            </>
          )}

          {/* Progress */}
          {job && job.status !== 'completed' && (
            <div style={{ padding: '20px', borderRadius: 'var(--radius)', background: 'var(--info-light)', color: 'var(--info)' }}>
              <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '8px' }}>
                {job.status === 'queued' ? 'Hàng đợi' : job.status === 'running' ? 'Đang xử lý' : job.status}
              </div>
              {job.progress?.message && (
                <div style={{ fontSize: 'var(--text-sm)', marginBottom: '8px' }}>{job.progress.message}</div>
              )}
              {job.progress?.percent !== undefined && (
                <div>
                  <div
                    style={{
                      height: '6px',
                      borderRadius: '3px',
                      background: 'var(--info)',
                      width: `${job.progress.percent}%`,
                      transition: 'width 0.6s',
                    }}
                  />
                  <div style={{ fontSize: 'var(--text-xs)', marginTop: '8px' }}>
                    {job.progress.percent.toFixed(1)}%
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Cue editor */}
          {cues.length > 0 && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }} className="font-bold">
                  Phụ đề ({cues.length} đoạn)
                </h3>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <select
                    value={exportFormat}
                    onChange={(e) => setExportFormat(e.target.value)}
                    style={{
                      padding: '8px 12px',
                      borderRadius: 'var(--radius)',
                      border: '1px solid var(--border)',
                      fontSize: 'var(--text-sm)',
                      background: 'var(--bg)',
                      color: 'var(--text)',
                    }}
                  >
                    <option value="srt">SRT</option>
                    <option value="vtt">VTT</option>
                    <option value="ass">ASS</option>
                  </select>
                  <button
                    onClick={exportSubtitle}
                    style={{
                      background: 'var(--info-light)',
                      color: 'var(--info)',
                      border: 'none',
                      padding: '8px 16px',
                      borderRadius: 'var(--radius)',
                      fontSize: 'var(--text-sm)',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Xuất
                  </button>
                  <button
                    onClick={() => {
                      setCues([]);
                      setFile(null);
                      setJob(null);
                    }}
                    style={{
                      background: 'var(--bg)',
                      color: 'var(--text-dim)',
                      border: '1px solid var(--border)',
                      padding: '8px 16px',
                      borderRadius: 'var(--radius)',
                      fontSize: 'var(--text-sm)',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Xử lý mới
                  </button>
                </div>
              </div>
              <div
                style={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-lg)',
                  padding: '24px',
                  maxHeight: '500px',
                  overflow: 'auto',
                }}
                className="scrollbar-thin"
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {cues.map((c, i) => (
                    <div
                      key={i}
                      style={{
                        padding: '12px',
                        background: editingIndex === i ? 'var(--primary-light)' : 'var(--bg)',
                        borderRadius: 'var(--radius)',
                        border: editingIndex === i ? '1px solid var(--primary)' : '1px solid var(--border)',
                      }}
                    >
                      {editingIndex === i ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                            <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', minWidth: '48px' }}>
                              Bắt đầu
                            </span>
                            <input
                              type="text"
                              value={timeRange.start}
                              onChange={(e) => setTimeRange({ ...timeRange, start: e.target.value })}
                              placeholder="00:00:00,000"
                              style={{
                                flex: 1,
                                padding: '6px 8px',
                                borderRadius: 'var(--radius-xs)',
                                border: '1px solid var(--border)',
                                fontSize: 'var(--text-sm)',
                              }}
                            />
                          </div>
                          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                            <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', minWidth: '48px' }}>
                              Kết thúc
                            </span>
                            <input
                              type="text"
                              value={timeRange.end}
                              onChange={(e) => setTimeRange({ ...timeRange, end: e.target.value })}
                              placeholder="00:00:00,000"
                              style={{
                                flex: 1,
                                padding: '6px 8px',
                                borderRadius: 'var(--radius-xs)',
                                border: '1px solid var(--border)',
                                fontSize: 'var(--text-sm)',
                              }}
                            />
                          </div>
                          <textarea
                            value={editText}
                            onChange={(e) => setEditText(e.target.value)}
                            rows={3}
                            style={{
                              padding: '8px',
                              borderRadius: 'var(--radius-xs)',
                              border: '1px solid var(--border)',
                              fontSize: 'var(--text-base)',
                              resize: 'vertical',
                              fontFamily: 'inherit',
                            }}
                          />
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <button
                              onClick={saveEdit}
                              style={{
                                background: 'var(--primary)',
                                color: '#fff',
                                border: 'none',
                                padding: '6px 12px',
                                borderRadius: 'var(--radius-xs)',
                                fontWeight: 600,
                                fontSize: 'var(--text-sm)',
                                cursor: 'pointer',
                              }}
                            >
                              Lưu
                            </button>
                            <button
                              onClick={() => {
                                setEditingIndex(null);
                                setEditText('');
                                setTimeRange({ start: '', end: '' });
                              }}
                              style={{
                                background: 'var(--bg)',
                                color: 'var(--text-dim)',
                                border: '1px solid var(--border)',
                                padding: '6px 12px',
                                borderRadius: 'var(--radius-xs)',
                                fontWeight: 600,
                                fontSize: 'var(--text-sm)',
                                cursor: 'pointer',
                              }}
                            >
                              Huỷ
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                          <div style={{ flex: 1 }}>
                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginBottom: '6px' }}>
                              {prettifyTime(c.start)} → {prettifyTime(c.end)}
                            </div>
                            <div style={{ fontSize: 'var(--text-base)', whiteSpace: 'pre-wrap' }}>
                              {c.text}
                            </div>
                          </div>
                          <button
                            onClick={() => startEdit(i)}
                            style={{
                              background: 'transparent',
                              color: 'var(--text-dim)',
                              border: 'none',
                              padding: '4px 8px',
                              fontSize: 'var(--text-xs)',
                              cursor: 'pointer',
                            }}
                          >
                            Sửa
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          {/* Tips */}
          <div style={{ background: 'var(--info-light)', border: '1px solid var(--info)', borderRadius: 'var(--radius-lg)', padding: '20px' }}>
            <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '12px', color: 'var(--info)' }}>
              💡 Mẹo
            </h4>
            <ul style={{ fontSize: 'var(--text-sm)', color: 'var(--text)', listStyle: 'none', padding: 0, margin: 0 }}>
              <li style={{ marginBottom: '8px' }}>• Sử dụng video có tiếng nói rõ ràng</li>
              <li style={{ marginBottom: '8px' }}>• Có thể chỉnh sửa thời gian và nội dung</li>
              <li>• Hỗ trợ export SRT, VTT, ASS</li>
            </ul>
          </div>

          {/* Features */}
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '20px' }}>
            <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '12px' }}>
              🎯 Tính năng
            </h4>
            <ul style={{ fontSize: 'var(--text-sm)', color: 'var(--text)', listStyle: 'none', padding: 0, margin: 0 }}>
              <li style={{ marginBottom: '8px' }}>• Nhận dạng ngôn ngữ tự động</li>
              <li style={{ marginBottom: '8px' }}>• Cắt đoạn phụ đề thông minh</li>
              <li style={{ marginBottom: '8px' }}>• Hỗ trợ song ngữ</li>
              <li>• Soạn thảo inline</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}