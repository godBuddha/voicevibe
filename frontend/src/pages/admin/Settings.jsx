import { useState, useEffect } from 'react';
import { useApi } from '../../hooks/useApi.jsx';

export default function AdminSettings() {
  const { api } = useApi();
  const [settings, setSettings] = useState({});
  const [editing, setEditing] = useState(null);
  const [editValue, setEditValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);

  useEffect(() => {
    loadSettings();
  }, [api]);

  const loadSettings = async () => {
    try {
      // Endpoint thật: GET /admin/settings → {settings: [{key, label, category,
      // is_secret, value, source, set_in_db}]}. Trang render object {key: value}
      // — chuyển tại đây; giá trị secret về sau bị mask, chỉ ghi đè khi đổi.
      const data = await api.get('/admin/settings');
      const map = {};
      for (const s of (data.settings || [])) map[s.key] = s.value ?? '';
      setSettings(map);
    } catch {}
  };

  const updateSetting = async (key, value) => {
    setLoading(true);
    try {
      // PUT /admin/settings/{key} {value} — upsert (tạo mới nếu chưa có).
      await api.put(`/admin/settings/${key}`, { body: { value } });
      setSettings({ ...settings, [key]: value });
      setEditing(null);
      setEditValue('');
    } catch (err) {
      alert('Lỗi khi lưu setting: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const addSetting = async () => {
    const key = newKey.trim();
    const val = newValue.trim();
    if (!key || !val) {
      alert('Vui lòng nhập cả key và value');
      return;
    }
    setLoading(true);
    try {
      await api.put(`/admin/settings/${key}`, { body: { value: val } });
      setSettings({ ...settings, [key]: val });
      setNewKey('');
      setNewValue('');
      setShowAddForm(false);
    } catch (err) {
      alert('Lỗi khi thêm setting: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const deleteSetting = async (key) => {
    if (!confirm(`Xoá setting "${key}"?`)) return;
    try {
      await api.del(`/admin/settings/${key}`);
      const newSettings = { ...settings };
      delete newSettings[key];
      setSettings(newSettings);
    } catch (err) {
      alert('Lỗi khi xoá setting: ' + err.message);
    }
  };

  const groupedSettings = Object.keys(settings).reduce((acc, key) => {
    const category = key.split('_')[0];
    if (!acc[category]) acc[category] = [];
    acc[category].push({ key, value: settings[key] });
    return acc;
  }, {});

  const getValueDisplay = (value) => {
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    if (typeof value === 'number') return value.toString();
    if (typeof value === 'object') return JSON.stringify(value, null, 2);
    return value;
  };

  return (
    <div style={{ padding: '40px', maxWidth: '1000px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '24px', fontWeight: 700 }}>
        Cài đặt hệ thống
      </h1>
      <p style={{ color: 'var(--text-dim)', marginBottom: '48px' }}>
        Quản lý các cấu hình và tham số hệ thống
      </p>

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
                placeholder="category subsection name"
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
      {Object.keys(groupedSettings).length === 0 && (
        <div style={{ textAlign: 'center', padding: '64px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)' }}>
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>⚙️</div>
          <div style={{ color: 'var(--text-dim)' }}>Chưa có cài đặt nào. Thêm cài đặt đầu tiên.</div>
        </div>
      )}

      {Object.keys(groupedSettings).map(category => (
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
          <h3 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, marginBottom: '20px', textTransform: 'capitalize' }}>
            {category}
          </h3>
          <div style={{ display: 'grid', gap: '16px' }}>
            {groupedSettings[category].map(({ key, value }) => (
              <div
                key={key}
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
                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-dim)' }}>
                  {key.replace(category + '_', '')}
                </div>
                <div>
                  {editing === key ? (
                    <input
                      type="text"
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      style={{
                        width: '100%',
                        padding: '6px 10px',
                        borderRadius: 'var(--radius-xs)',
                        border: '1px solid var(--primary)',
                        fontSize: 'var(--text-sm)',
                        background: 'var(--surface)',
                        color: 'var(--text)',
                      }}
                      autoFocus
                    />
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
                      {typeof value === 'object' ? (
                        <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{getValueDisplay(value)}</pre>
                      ) : (
                        getValueDisplay(value)
                      )}
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  {editing === key ? (
                    <>
                      <button
                        onClick={() => updateSetting(key, editValue)}
                        disabled={loading}
                        style={{
                          background: 'var(--primary)',
                          color: '#fff',
                          border: 'none',
                          padding: '4px 8px',
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
                          padding: '4px 8px',
                          borderRadius: '4px',
                          fontSize: 'var(--text-xs)',
                          cursor: 'pointer',
                        }}
                      >
                        Huỷ
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={() => {
                          setEditing(key);
                          setEditValue(getValueDisplay(value));
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
                      <button
                        onClick={() => deleteSetting(key)}
                        style={{
                          background: 'var(--danger-light)',
                          color: 'var(--danger)',
                          border: 'none',
                          padding: '4px 8px',
                          borderRadius: '4px',
                          fontSize: 'var(--text-xs)',
                          cursor: 'pointer',
                        }}
                      >
                        Xoá
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}