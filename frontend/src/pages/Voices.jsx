import { useState, useRef, useEffect } from 'react';
import { useApi } from '../hooks/useApi.jsx';

export default function Voices() {
  const { api } = useApi();
  const fileInputRef = useRef(null);
  const [voices, setVoices] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newVoiceName, setNewVoiceName] = useState('');
  const [newVoiceFiles, setNewVoiceFiles] = useState([]);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const data = await api.get('/v1/voices');
        setVoices(data);
      } catch {}
    })();
  }, [api]);

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files || []);
    setNewVoiceFiles(files.slice(0, 3));
  };

  const createVoice = async () => {
    if (!newVoiceName.trim() || newVoiceFiles.length === 0) {
      alert('Vui lòng nhập tên và chọn ít nhất 1 file mẫu');
      return;
    }
    setIsUploading(true);
    setUploadProgress(0);
    try {
      const formData = new FormData();
      formData.append('name', newVoiceName);
      newVoiceFiles.forEach((f, i) => formData.append(`sample_${i}`, f));
      await api.post('/v1/voices/upload', { body: formData, isMultipart: true });
      const newVoice = {
        id: Date.now(),
        name: newVoiceName,
        type: 'clone',
        gender: 'unknown',
        accent: 'custom',
      };
      setVoices((prev) => [...prev, newVoice]);
      setShowCreate(false);
      setNewVoiceName('');
      setNewVoiceFiles([]);
      setUploadProgress(100);
    } catch (err) {
      alert('Lỗi khi tạo giọng: ' + err.message);
    } finally {
      setIsUploading(false);
    }
  };

  const deleteVoice = async (id) => {
    if (!confirm('Bạn có chắc muốn xoá giọng này?')) return;
    setVoices((prev) => prev.filter((v) => v.id !== id));
  };

  return (
    <div style={{ padding: '40px', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
        <div>
          <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '8px', fontWeight: 700 }}>
            Giọng Clone
          </h1>
          <p style={{ color: 'var(--text-dim)' }}>
            Tạo và quản lý giọng của riêng bạn từ mẫu âm thanh
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          style={{
            background: 'var(--gradient)',
            color: '#fff',
            border: 'none',
            padding: '12px 24px',
            borderRadius: 'var(--radius)',
            fontSize: 'var(--text-base)',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          + Tạo giọng mới
        </button>
      </div>

      {/* Create voice form */}
      {showCreate && (
        <div
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
            padding: '32px',
            marginBottom: '32px',
          }}
        >
          <h3 style={{ fontSize: 'var(--text-xl)', marginBottom: '24px', fontWeight: 700 }}>
            Tạo giọng mới
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px' }}>
            <div>
              <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '8px', fontWeight: 600 }}>
                Tên giọng
              </label>
              <input
                type="text"
                placeholder="Ví dụ: Giọng MC sự kiện"
                value={newVoiceName}
                onChange={(e) => setNewVoiceName(e.target.value)}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  borderRadius: 'var(--radius)',
                  border: '1px solid var(--border)',
                  fontSize: 'var(--text-base)',
                  background: 'var(--bg)',
                  color: 'var(--text)',
                }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '8px', fontWeight: 600 }}>
                Mẫu âm thanh (1-3 file, mỗi file 5-8 giây)
              </label>
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileSelect}
                accept="audio/*"
                multiple
                style={{ width: '100%' }}
              />
              {newVoiceFiles.length > 0 && (
                <div style={{ marginTop: '8px', fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                  {newVoiceFiles.length} file đã chọn: {newVoiceFiles.map(f => f.name).join(', ')}
                </div>
              )}
            </div>
          </div>
          {isUploading && (
            <div style={{ marginTop: '16px' }}>
              <div style={{ height: '4px', borderRadius: '2px', background: 'var(--border)', overflow: 'hidden' }}>
                <div style={{ height: '100%', borderRadius: '2px', background: 'var(--primary)', width: `${uploadProgress}%`, transition: 'width 0.3s' }} />
              </div>
            </div>
          )}
          <div style={{ display: 'flex', gap: '16px', marginTop: '24px' }}>
            <button
              onClick={createVoice}
              disabled={isUploading}
              style={{
                background: 'var(--gradient)',
                color: '#fff',
                border: 'none',
                padding: '10px 24px',
                borderRadius: 'var(--radius)',
                fontWeight: 600,
                cursor: isUploading ? 'not-allowed' : 'pointer',
                opacity: isUploading ? 0.6 : 1,
              }}
            >
              {isUploading ? 'Đang tải lên...' : 'Tạo giọng'}
            </button>
            <button
              onClick={() => {
                setShowCreate(false);
                setNewVoiceName('');
                setNewVoiceFiles([]);
              }}
              style={{
                background: 'var(--bg)',
                color: 'var(--text-dim)',
                border: '1px solid var(--border)',
                padding: '10px 24px',
                borderRadius: 'var(--radius)',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Huỷ
            </button>
          </div>
        </div>
      )}

      {/* Voices grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '20px' }}>
        {voices.map((voice) => (
          <div
            key={voice.id}
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              padding: '24px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <div
                style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: 'var(--radius-full)',
                  background: voice.type === 'clone' ? 'var(--accent-light)' : 'var(--primary-light)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '24px',
                }}
              >
                {voice.gender === 'female' ? '👩' : voice.gender === 'male' ? '👨' : '🎤'}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 'var(--text-base)', marginBottom: '4px' }}>
                  {voice.name}
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                  {voice.type === 'clone' ? 'Giọng clone' : 'Giọng có sẵn'} • {voice.accent}
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                style={{
                  flex: 1,
                  padding: '8px',
                  borderRadius: 'var(--radius)',
                  background: 'var(--primary-light)',
                  color: 'var(--primary)',
                  fontWeight: 600,
                  fontSize: 'var(--text-sm)',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                Dùng ngay
              </button>
              {voice.type === 'clone' && (
                <button
                  onClick={() => deleteVoice(voice.id)}
                  style={{
                    padding: '8px 12px',
                    borderRadius: 'var(--radius)',
                    background: 'var(--danger-light)',
                    color: 'var(--danger)',
                    fontWeight: 600,
                    fontSize: 'var(--text-sm)',
                    border: 'none',
                    cursor: 'pointer',
                  }}
                >
                  Xoá
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}