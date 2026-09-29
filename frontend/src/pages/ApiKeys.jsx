import { useState, useEffect } from 'react';
import { useApi } from '../hooks/useApi.jsx';

export default function ApiKeys() {
  const { api } = useApi();
  const [keys, setKeys] = useState([]);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [newPermissions, setNewPermissions] = useState('full');
  const [wasCreated, setWasCreated] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchKeys();
  }, [api]);

  const fetchKeys = async () => {
    try {
      const data = await api.get('/v1/keys');
      setKeys(data);
    } catch {}
  };

  const createKey = async () => {
    if (!newKeyName.trim()) return;
    setLoading(true);
    try {
      const res = await api.post('/v1/keys', {
        body: { name: newKeyName, permissions: newPermissions },
      });
      setKeys([{ ...res, name: newKeyName, permissions: newPermissions, created: new Date() }, ...keys]);
      setWasCreated(res.key);
      setShowCreateModal(false);
      setNewKeyName('');
      setNewPermissions('full');
    } catch (err) {
      alert('Lỗi khi tạo API key: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const deleteKey = async (id) => {
    if (!confirm('Bạn có chắc muốn xoá API key này?')) return;
    try {
      await api.del(`/v1/keys/${id}`);
      setKeys(keys.filter(k => k.id !== id));
    } catch (err) {
      alert('Lỗi khi xoá key: ' + err.message);
    }
  };

  const formatDate = (date) => {
    const d = new Date(date);
    return d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const hideCreated = () => setWasCreated(null);

  return (
    <div style={{ padding: '40px', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
        <div>
          <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '8px', fontWeight: 700 }}>
            API Keys
          </h1>
          <p style={{ color: 'var(--text-dim)' }}>
            Quản lý khóa API để truy cập các dịch vụ VoiceVibe
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
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
          + Tạo API Key
        </button>
      </div>

      {/* Display new key modal */}
      {wasCreated && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 'var(--z-modal)',
        }}>
          <div
            style={{
              background: 'var(--surface)',
              borderRadius: 'var(--radius-lg)',
              padding: '32px',
              maxWidth: '500px',
              width: '90%',
            }}
            onMouseDown={hideCreated}
          >
            <h3 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, marginBottom: '16px' }}>
              API Key mới đã tạo
            </h3>
            <p style={{ fontSize: 'var(--text-base)', color: 'var(--text-dim)', marginBottom: '24px' }}>
              Đây là lần duy nhất bạn có thể xem key này. Vui lòng sao lưu ngay.
            </p>
            <div
              style={{
                background: 'var(--bg)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
                padding: '12px',
                fontFamily: 'monospace',
                fontSize: '14px',
                wordBreak: 'break-all',
                marginBottom: '24px',
                userSelect: 'all',
                cursor: 'text',
              }}
            >
              {wasCreated}
            </div>
            <button
              onClick={hideCreated}
              style={{
                background: 'var(--gradient)',
                color: '#fff',
                border: 'none',
                padding: '12px 24px',
                borderRadius: 'var(--radius)',
                fontWeight: 600,
                cursor: 'pointer',
                width: '100%',
              }}
            >
              Đã sao lưu
            </button>
          </div>
        </div>
      )}

      {/* Create key modal */}
      {showCreateModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 'var(--z-modal)',
        }}
        onClick={() => !loading && setShowCreateModal(false)}
        >
          <div
            style={{
              background: 'var(--surface)',
              borderRadius: 'var(--radius-lg)',
              padding: '32px',
              maxWidth: '400px',
              width: '90%',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, marginBottom: '24px' }}>
              Tạo API Key mới
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '8px', fontWeight: 600 }}>
                  Tên key
                </label>
                <input
                  type="text"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  placeholder="Ví dụ: Production API"
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    borderRadius: 'var(--radius)',
                    border: '1px solid var(--border)',
                    fontSize: 'var(--text-base)',
                    background: 'var(--bg)',
                    color: 'var(--text)',
                  }}
                  required
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '8px', fontWeight: 600 }}>
                  Quyền hạn
                </label>
                <select
                  value={newPermissions}
                  onChange={(e) => setNewPermissions(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    borderRadius: 'var(--radius)',
                    border: '1px solid var(--border)',
                    fontSize: 'var(--text-base)',
                    background: 'var(--bg)',
                    color: 'var(--text)',
                  }}
                >
                  <option value="full">Toàn quyền</option>
                  <option value="limited">Giới hạn (chỉ đọc)</option>
                  <option value="micropayment">Micropayment</option>
                </select>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '12px', marginTop: '24px' }}>
              <button
                onClick={createKey}
                disabled={!newKeyName.trim() || loading}
                style={{
                  flex: 1,
                  background: 'var(--gradient)',
                  color: '#fff',
                  border: 'none',
                  padding: '10px 20px',
                  borderRadius: 'var(--radius)',
                  fontWeight: 600,
                  cursor: loading ? 'not-allowed' : 'pointer',
                  opacity: loading ? 0.6 : 1,
                }}
              >
                {loading ? 'Đang tạo...' : 'Tạo'}
              </button>
              <button
                onClick={() => {
                  if (!loading) {
                    setShowCreateModal(false);
                    setNewKeyName('');
                    setNewPermissions('full');
                  }
                }}
                style={{
                  background: 'var(--bg)',
                  color: 'var(--text-dim)',
                  border: '1px solid var(--border)',
                  padding: '10px 20px',
                  borderRadius: 'var(--radius)',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Huỷ
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Keys list */}
      <div style={{ display: 'grid', gap: '20px' }}>
        {keys.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '64px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)' }}>
            <div style={{ fontSize: '48px', marginBottom: '16px' }}>🔑</div>
            <div style={{ color: 'var(--text-dim)' }}>Chưa có API key nào. Tạo key đầu tiên để bắt đầu.</div>
          </div>
        ) : (
          keys.map(key => (
            <div
              key={key.id}
              style={{
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-lg)',
                padding: '24px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div style={{ cursor: 'pointer' }} onClick={() => navigator.clipboard.writeText(key.key)}>
                <div style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: '8px' }}>
                  {key.name}
                </div>
                <div
                  style={{
                    fontSize: 'var(--text-xs)',
                    color: 'var(--text-dim)',
                    fontFamily: 'monospace',
                    background: 'var(--bg)',
                    padding: '4px 8px',
                    borderRadius: 'var(--radius-xs)',
                    border: '1px solid var(--border)',
                    marginBottom: '8px',
                    maxWidth: '500px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                  title={key.key}
                >
                  {key.key}
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                  Tạo: {formatDate(key.created)} • Quyền: {key.permissions === 'full' ? 'Toàn quyền' : key.permissions === 'limited' ? 'Giới hạn' : 'Micropayment'}
                  {key.lastUsed && ` • Lần dùng cuối: ${formatDate(key.lastUsed)}`}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <button
                  onClick={() => navigator.clipboard.writeText(key.key)}
                  style={{
                    background: 'var(--info-light)',
                    color: 'var(--info)',
                    border: 'none',
                    padding: '8px 16px',
                    borderRadius: 'var(--radius)',
                    fontWeight: 600,
                    fontSize: 'var(--text-sm)',
                    cursor: 'pointer',
                  }}
                >
                  📋 Sao chép
                </button>
                <button
                  onClick={() => deleteKey(key.id)}
                  style={{
                    background: 'var(--danger-light)',
                    color: 'var(--danger)',
                    border: 'none',
                    padding: '8px 16px',
                    borderRadius: 'var(--radius)',
                    fontWeight: 600,
                    fontSize: 'var(--text-sm)',
                    cursor: 'pointer',
                  }}
                >
                  Xoá
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}