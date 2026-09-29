import { useState, useEffect } from 'react';
import { useApi } from '../hooks/useApi.jsx';

export default function ApiKeys() {
  const { api } = useApi();
  const [keys, setKeys] = useState([]);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [wasCreated, setWasCreated] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchKeys();
  }, [api]);

  const fetchKeys = async () => {
    try {
      // useApi đã adapter '/v1/keys' → mảng (trước đây setKeys({keys: []}) rồi
      // keys.map → TypeError, trang trắng — đã gặp thật khi dò UI).
      setKeys(await api.get('/v1/keys'));
    } catch (e) {
      console.error('tải danh sách key thất bại', e);
    }
  };

  const createKey = async () => {
    setLoading(true);
    setError(null);
    try {
      // Backend KHÔNG nhận tên/quyền hạn — mỗi lần gọi là 1 key full-quyền 60
      // req/phút. Form "Tên key / Quyền hạn" của bản mock đã bịa, giờ bỏ để
      // không hứa hẹn thứ server không lưu.
      const res = await api.post('/v1/keys', { body: {} });
      setWasCreated(res.key);
      setShowCreateModal(false);
      await fetchKeys();
    } catch (err) {
      setError('Lỗi khi tạo API key: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const deleteKey = async (prefix) => {
    if (!confirm('Bạn có chắc muốn thu hồi API key này?')) return;
    try {
      // Thu hồi theo PREFIX (12 ký tự đầu) — backend chấp nhận cả raw key lẫn
      // prefix. Trước đây gọi DELETE /v1/keys/undefined (list không có id).
      await api.del(`/v1/keys/${prefix}`);
      await fetchKeys();
    } catch (err) {
      setError('Lỗi khi thu hồi key: ' + err.message);
    }
  };

  const formatDate = (sec) => {
    if (!sec) return '—';
    return new Date(sec * 1000).toLocaleString('vi-VN', {
      day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
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
            Quản lý khóa API để truy cập các dịch vụ VoiceVibe (60 req/phút mỗi key)
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

      {/* Error */}
      {error && (
        <div style={{
          padding: '16px', borderRadius: 'var(--radius)', marginBottom: '24px',
          background: 'var(--danger-light)', color: 'var(--danger)',
        }}>
          {error}
        </div>
      )}

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
            <h3 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, marginBottom: '16px' }}>
              Tạo API Key mới
            </h3>
            <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '24px' }}>
              Key có toàn quyền truy cập API bằng tài khoản của bạn. Máy gọi gửi header <code>X-API-Key</code>.
            </p>
            <div style={{ display: 'flex', gap: '12px', marginTop: '24px' }}>
              <button
                onClick={createKey}
                disabled={loading}
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
                  if (!loading) setShowCreateModal(false);
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
          keys.map((k, i) => (
            <div
              key={`${k.prefix}-${i}`}
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
              <div>
                <div style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: '8px' }}>
                  {k.key}
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                  Tạo: {formatDate(k.created_at)} • Hạn mức: {k.rate_limit_per_min} req/phút • {k.active ? 'Đang hoạt động' : 'Đã thu hồi'}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <button
                  onClick={() => navigator.clipboard.writeText(k.prefix).catch(() => {})}
                  title="Sao chép tiền tố (dùng để nhận diện, KHÔNG dùng để gọi API)"
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
                  📋 Sao chép tiền tố
                </button>
                <button
                  onClick={() => deleteKey(k.prefix)}
                  disabled={!k.active}
                  style={{
                    background: 'var(--danger-light)',
                    color: 'var(--danger)',
                    border: 'none',
                    padding: '8px 16px',
                    borderRadius: 'var(--radius)',
                    fontWeight: 600,
                    fontSize: 'var(--text-sm)',
                    cursor: k.active ? 'pointer' : 'not-allowed',
                    opacity: k.active ? 1 : 0.5,
                  }}
                >
                  Thu hồi
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
