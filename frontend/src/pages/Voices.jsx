import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApi } from '../hooks/useApi.jsx';

export default function Voices() {
  const { api } = useApi();
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const [voices, setVoices] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newVoiceName, setNewVoiceName] = useState('');
  const [newVoiceFile, setNewVoiceFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState(null);

  // Danh sách thật từ GET /v1/voices (trước đây gọi 405 → luôn trống; sau đó
  // còn tự bịa giọng {id: Date.now()} gắn vào UI để "trông như tạo được").
  const loadVoices = async () => {
    try {
      setVoices(await api.get('/v1/voices'));
      return true;
    } catch (e) {
      console.error('tải danh sách giọng thất bại', e);
      return false;
    }
  };

  useEffect(() => {
    loadVoices();
  }, [api]);

  const createVoice = async () => {
    if (!newVoiceName.trim() || !newVoiceFile) {
      setError('Vui lòng nhập tên và chọn 1 file mẫu');
      return;
    }
    setIsUploading(true);
    setError(null);
    try {
      // Backend nhận Form `name`, `lang`, MỘT file `file` — trước đây SPA gửi
      // `sample_0..2` (không field nào khớp) → 422.
      const formData = new FormData();
      formData.append('name', newVoiceName);
      formData.append('lang', 'auto');
      formData.append('file', newVoiceFile);
      await api.post('/v1/voices/upload', { body: formData, isMultipart: true });
      // Tải lại danh sách thật — giọng mới xuất hiện như mọi người dùng khác thấy.
      await loadVoices();
      setShowCreate(false);
      setNewVoiceName('');
      setNewVoiceFile(null);
    } catch (err) {
      setError('Lỗi khi tạo giọng: ' + err.message);
    } finally {
      setIsUploading(false);
    }
  };

  const deleteVoice = async (id) => {
    if (!confirm('Bạn có chắc muốn xoá giọng này?')) return;
    try {
      // Xoá THẬT trên server (trước đây chỉ lọc mảng UI — tải lại trang giọng
      // quay lại như chưa xoá).
      await api.del(`/v1/voices/${id}`);
      await loadVoices();
    } catch (err) {
      alert('Lỗi khi xoá giọng: ' + err.message);
    }
  };

  return (
    <div style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
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
            padding: '10px 14px',
            borderRadius: 'var(--radius)',
            fontSize: 'var(--text-base)',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          + Tạo giọng mới
        </button>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          padding: '12px', borderRadius: 'var(--radius)', marginBottom: '14px',
          background: 'var(--danger-light)', color: 'var(--danger)',
        }}>
          {error}
        </div>
      )}

      {/* Create voice form */}
      {showCreate && (
        <div
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
            padding: '16px',
            marginBottom: '16px',
          }}
        >
          <h3 style={{ fontSize: 'var(--text-xl)', marginBottom: '14px', fontWeight: 700 }}>
            Tạo giọng mới
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
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
                  padding: '10px 10px',
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
                Mẫu âm thanh (1 file, 5-10 giây, giọng rõ)
              </label>
              <input
                type="file"
                ref={fileInputRef}
                onChange={(e) => setNewVoiceFile(e.target.files?.[0] || null)}
                accept="audio/*"
                style={{ width: '100%' }}
              />
              {newVoiceFile && (
                <div style={{ marginTop: '8px', fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                  Đã chọn: {newVoiceFile.name}
                </div>
              )}
            </div>
          </div>
          <div style={{ display: 'flex', gap: '12px', marginTop: '14px' }}>
            <button
              onClick={createVoice}
              disabled={isUploading}
              style={{
                background: 'var(--gradient)',
                color: '#fff',
                border: 'none',
                padding: '10px 14px',
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
                setNewVoiceFile(null);
                setError(null);
              }}
              style={{
                background: 'var(--bg)',
                color: 'var(--text-dim)',
                border: '1px solid var(--border)',
                padding: '10px 14px',
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
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
        {voices.map((voice) => (
          <div
            key={voice.id}
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              padding: '14px',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div
                style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: 'var(--radius-full)',
                  background: 'var(--primary-light)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '24px',
                }}
              >
                🎤
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 'var(--text-base)', marginBottom: '4px' }}>
                  {voice.name}
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                  Giọng clone • {voice.lang} • {voice.engine}
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={() => navigate('/tts')}
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
              <button
                onClick={() => deleteVoice(voice.id)}
                style={{
                  padding: '8px 10px',
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
            </div>
          </div>
        ))}
      </div>
      {!voices.length && !showCreate && (
        <div style={{ textAlign: 'center', padding: '64px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)' }}>
          <div style={{ fontSize: '48px', marginBottom: '12px' }}>🎤</div>
          <div style={{ color: 'var(--text-dim)' }}>Chưa có giọng nào. Tạo giọng đầu tiên từ một mẫu 5-10 giây.</div>
        </div>
      )}
    </div>
  );
}
