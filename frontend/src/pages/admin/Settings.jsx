import { useState, useEffect } from 'react';
import { useApi } from '../../hooks/useApi.jsx';

export default function AdminSettings() {
  const { api } = useApi();
  const [rows, setRows] = useState([]); // object gốc: {key,label,category,is_secret,value,source,set_in_db}
  const [editing, setEditing] = useState(null);
  const [editValue, setEditValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);

  useEffect(() => {
    loadSettings();
  }, [api]);

  const loadSettings = async () => {
    try {
      // Giữ NGUYÊN metadata của từng setting. Trước đây gộp thành {key: value}
      // làm mất `is_secret` → người sửa secret nhận giá trị MẶT-NẠ ("••••1234")
      // prefilled và bấm Lưu là ghi đè token thật bằng rác (đã gặp thật).
      const data = await api.get('/v1/admin/settings');
      setRows(data.settings || []);
    } catch (e) {
      console.error('tải cài đặt thất bại', e);
    }
  };

  const updateSetting = async (row, value) => {
    // SECRET: ô sửa luôn rỗng. Để trống = "giữ nguyên" — KHÔNG gọi PUT.
    // (Gửi chính chuỗi mặt-nạ về là hủy hoại token — bug nghiêm trọng nhất
    // của trang này trước khi sửa.)
    if (row.is_secret && !value.trim()) {
      setEditing(null);
      setEditValue('');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await api.put(`/v1/admin/settings/${row.key}`, { body: { value } });
      setEditing(null);
      setEditValue('');
      await loadSettings();
    } catch (err) {
      setError('Lỗi khi lưu setting: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const addSetting = async () => {
    const key = newKey.trim();
    const val = newValue.trim();
    if (!key || !val) {
      setError('Vui lòng nhập cả key và value');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await api.put(`/v1/admin/settings/${key}`, { body: { value: val } });
      setNewKey('');
      setNewValue('');
      setShowAddForm(false);
      await loadSettings();
    } catch (err) {
      setError('Lỗi khi thêm setting: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const deleteSetting = async (row) => {
    if (!confirm(`Xoá setting "${row.key}" (quay về giá trị mặc định)?`)) return;
    try {
      await api.del(`/v1/admin/settings/${row.key}`);
      await loadSettings();
    } catch (err) {
      setError('Lỗi khi xoá setting: ' + err.message);
    }
  };

  // Nhóm theo ĐOẠN TRƯỚC DẤU CHẤM (`translate.backend` → nhóm `translate`) — trước đây
  // tách theo `_` nên từng key thành một nhóm riêng lẻ, trang dài lê thê.
  const grouped = rows.reduce((acc, row) => {
    const category = row.key.split('.')[0] || 'khác';
    (acc[category] = acc[category] || []).push(row);
    return acc;
  }, {});

  const displayValue = (row) => {
    const v = row.value;
    if (v === null || v === undefined || v === '') return <em style={{ opacity: 0.5 }}>chưa đặt</em>;
    if (typeof v === 'boolean') return v ? 'true' : 'false';
    return String(v);
  };

  const sourceBadge = (src) => ({
    db: { text: 'DB', bg: 'var(--primary-light)', color: 'var(--primary)' },
    env: { text: 'env', bg: 'var(--info-light)', color: 'var(--info)' },
  }[src] || { text: 'mặc định', bg: 'var(--bg)', color: 'var(--text-dim)' });

  return (
    <div style={{ padding: '40px', maxWidth: '1000px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '24px', fontWeight: 700 }}>
        Cài đặt hệ thống
      </h1>
      <p style={{ color: 'var(--text-dim)', marginBottom: '48px' }}>
        Quản lý các cấu hình và tham số hệ thống. Giá trị secret hiển thị dạng mặt-nạ;
        muốn đổi thì nhập giá trị MỚI, để trống là giữ nguyên.
      </p>

      {/* Error */}
      {error && (
        <div style={{
          padding: '16px', borderRadius: 'var(--radius)', marginBottom: '24px',
          background: 'var(--danger-light)', color: 'var(--danger)',
        }}>
          {error}
        </div>
      )}

      {/* Add new setting form */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '24px', marginBottom: '32px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 600 }}>Thêm cài đặt mới</h3>
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            style={{
              background: 'var(--gradient)',
              color: '#fff',
              border: 'none',
              padding: '8px 16px',
              borderRadius: 'var(--radius)',
              fontSize: 'var(--text-sm)',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {showAddForm ? 'Huỷ' : '+ Thêm'}
          </button>
        </div>
        {showAddForm && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr auto', gap: '16px', alignItems: 'end' }}>
            <div>
              <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '8px', fontWeight: 600 }}>
                Key
              </label>
              <input
                type="text"
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                placeholder="ví dụ: translate.model"
                style={{
                  width: '100%',
                  padding: '8px 12px',
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
                Value
              </label>
              <input
                type="text"
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder="Giá trị"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  borderRadius: 'var(--radius)',
                  border: '1px solid var(--border)',
                  fontSize: 'var(--text-base)',
                  background: 'var(--bg)',
                  color: 'var(--text)',
                }}
              />
            </div>
            <button
              onClick={addSetting}
              disabled={loading}
              style={{
                background: 'var(--primary)',
                color: '#fff',
                border: 'none',
                padding: '8px 16px',
                borderRadius: 'var(--radius)',
                fontWeight: 600,
                cursor: 'pointer',
                opacity: loading ? 0.6 : 1,
              }}
            >
              {loading ? 'Đang lưu...' : 'Lưu'}
            </button>
          </div>
        )}
      </div>

      {/* Settings by category */}
      {Object.keys(grouped).length === 0 && (
        <div style={{ textAlign: 'center', padding: '64px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)' }}>
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>⚙️</div>
          <div style={{ color: 'var(--text-dim)' }}>Chưa có cài đặt nào. Thêm cài đặt đầu tiên.</div>
        </div>
      )}

      {Object.keys(grouped).map(category => (
        <div
          key={category}
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
            padding: '24px',
            marginBottom: '24px',
          }}
        >
          <h3 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, marginBottom: '20px' }}>
            {category}
          </h3>
          <div style={{ display: 'grid', gap: '16px' }}>
            {grouped[category].map((row) => {
              const badge = sourceBadge(row.source);
              return (
                <div
                  key={row.key}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '240px 1fr auto',
                    gap: '16px',
                    alignItems: 'center',
                    padding: '12px',
                    background: 'var(--bg)',
                    borderRadius: 'var(--radius)',
                  }}
                >
                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                      {row.label || row.key}
                    </div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', fontFamily: 'monospace' }}>
                      {row.key}
                    </div>
                  </div>
                  <div>
                    {editing === row.key ? (
                      <div>
                        <input
                          type={row.is_secret ? 'password' : 'text'}
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          placeholder={row.is_secret ? 'Nhập giá trị MỚI (để trống = giữ nguyên)' : ''}
                          autoFocus
                          style={{
                            width: '100%',
                            padding: '6px 10px',
                            borderRadius: 'var(--radius-xs)',
                            border: '1px solid var(--primary)',
                            fontSize: 'var(--text-sm)',
                            background: 'var(--surface)',
                            color: 'var(--text)',
                          }}
                        />
                        <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                          <button
                            onClick={() => updateSetting(row, editValue)}
                            disabled={loading}
                            style={{
                              background: 'var(--primary)',
                              color: '#fff',
                              border: 'none',
                              padding: '4px 10px',
                              borderRadius: '4px',
                              fontSize: 'var(--text-xs)',
                              cursor: 'pointer',
                            }}
                          >
                            Lưu
                          </button>
                          <button
                            onClick={() => {
                              setEditing(null);
                              setEditValue('');
                            }}
                            style={{
                              background: 'var(--bg)',
                              color: 'var(--text-dim)',
                              border: '1px solid var(--border)',
                              padding: '4px 10px',
                              borderRadius: '4px',
                              fontSize: 'var(--text-xs)',
                              cursor: 'pointer',
                            }}
                          >
                            Huỷ
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div
                        style={{
                          padding: '6px 10px',
                          borderRadius: 'var(--radius-xs)',
                          background: 'var(--surface)',
                          fontSize: 'var(--text-sm)',
                          color: 'var(--text)',
                          wordWrap: 'break-word',
                          minHeight: '20px',
                        }}
                      >
                        {displayValue(row)}
                      </div>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    {editing !== row.key && (
                      <>
                        <span
                          title={`nguồn giá trị: ${row.source}`}
                          style={{
                            fontSize: '10px', padding: '2px 6px', borderRadius: '4px',
                            background: badge.bg, color: badge.color, fontWeight: 700,
                          }}
                        >
                          {badge.text}
                        </span>
                        <button
                          onClick={() => {
                            setEditing(row.key);
                            // SECRET: ô sửa luôn RỖNG — không prefilled mặt-nạ.
                            setEditValue(row.is_secret ? '' : (typeof row.value === 'string' || typeof row.value === 'number' || typeof row.value === 'boolean' ? String(row.value) : ''));
                          }}
                          style={{
                            background: 'var(--primary-light)',
                            color: 'var(--primary)',
                            border: 'none',
                            padding: '4px 8px',
                            borderRadius: '4px',
                            fontSize: 'var(--text-xs)',
                            cursor: 'pointer',
                          }}
                        >
                          Sửa
                        </button>
                        {row.set_in_db && (
                          <button
                            onClick={() => deleteSetting(row)}
                            style={{
                              background: 'var(--danger-light)',
                              color: 'var(--danger)',
                              border: 'none',
                              padding: '4px 8px',
                              borderRadius: '4px',
                              fontSize: 'var(--text-xs)',
                              cursor: 'pointer',
                            }}
                            title="Chỉ xóa được giá trị đặt trong DB (mặc định/env chỉ đọc)"
                          >
                            Xoá
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
