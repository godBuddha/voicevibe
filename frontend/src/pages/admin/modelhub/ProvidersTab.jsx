import { useState } from 'react';
import { RefreshCw, Eye, Pencil, Trash2, Plus, Power, SearchCheck, LoaderCircle } from 'lucide-react';

// Nút action nhỏ dùng chung trong tab
const btn = (bg, color) => ({
  background: bg, color, border: 'none', padding: '4px 9px',
  borderRadius: 'var(--radius-xs)', fontSize: 'var(--text-xs)',
  fontWeight: 600, cursor: 'pointer', display: 'inline-flex',
  alignItems: 'center', gap: '4px', whiteSpace: 'nowrap',
});
const input = {
  width: '100%', padding: '7px 10px', borderRadius: 'var(--radius-sm)',
  border: '1px solid var(--border)', fontSize: 'var(--text-sm)',
  background: 'var(--bg)', color: 'var(--text)',
};

const fmtSynced = (ts) => {
  if (!ts) return 'chưa đồng bộ';
  const mins = Math.floor((Date.now() - ts * 1000) / 60000);
  if (mins < 1) return 'vừa đồng bộ';
  if (mins < 60) return `đồng bộ ${mins} phút trước`;
  const h = Math.floor(mins / 60);
  if (h < 24) return `đồng bộ ${h} giờ trước`;
  return `đồng bộ ${Math.floor(h / 24)} ngày trước`;
};

export default function ProvidersTab({ providers, api, notify, reload, onViewModels, loading, setLoading }) {
  // editing = provider đang sửa | 'NEW' khi tạo mới (modal chung, đủ field —
  // hết window.prompt x4 của bản cũ)
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({});
  const [syncing, setSyncing] = useState(null);

  const openEdit = (p = null) => {
    setEditing(p ? p.id : 'NEW');
    setForm(p ? { ...p, api_key: '' } : { name: '', kind: 'openai', base_url: '', api_key: '', prefix_id: '' });
  };

  const save = async () => {
    if (!form.name || !form.base_url) {
      notify('Thiếu tên hoặc Base URL.', 'err');
      return;
    }
    setLoading(true);
    try {
      const body = {
        name: form.name, kind: form.kind, base_url: form.base_url,
        enabled: form.enabled !== false, prefix_id: form.prefix_id || undefined,
      };
      // PATCH semantics: chỉ gửi api_key khi người dùng NHẬP MỚI (để trống = giữ key cũ)
      if (form.api_key) body.api_key = form.api_key;
      if (editing === 'NEW') {
        await api.post('/v1/admin/providers', { body: { ...body, api_key: form.api_key || undefined } });
      } else {
        await api.patch(`/v1/admin/providers/${editing}`, { body });
      }
      setEditing(null);
      await reload();
      notify('Đã lưu provider.');
    } catch (err) {
      notify('Lỗi khi lưu provider: ' + err.message, 'err');
    } finally {
      setLoading(false);
    }
  };

  const sync = async (id, name) => {
    setSyncing(id);
    try {
      const res = await api.post(`/v1/admin/providers/${id}/sync`);
      notify(`Đồng bộ ${name}: ${res.synced} model (${res.added} thêm · ${res.updated} cập nhật · ${res.removed} gỡ) — ${res.duration_ms}ms`);
      await reload();
    } catch (err) {
      notify('Lỗi đồng bộ: ' + err.message, 'err');
    } finally {
      setSyncing(null);
    }
  };

  const test = async (id, name) => {
    try {
      const res = await api.post(`/v1/admin/providers/${id}/test`);
      notify(res.ok ? `${name}: kết nối OK — ${res.detail}` : `${name}: LỖI — ${res.detail}`, res.ok ? 'ok' : 'err');
    } catch (err) {
      notify('Lỗi kết nối: ' + err.message, 'err');
    }
  };

  const toggle = async (p) => {
    try {
      await api.patch(`/v1/admin/providers/${p.id}`, { body: { enabled: !p.enabled } });
      await reload();
    } catch (err) {
      notify('Lỗi: ' + err.message, 'err');
    }
  };

  const remove = async (p) => {
    if (!window.confirm(`Xoá provider "${p.name}"? Registry model của nó (${p.models_count ?? 0}) cũng bị xoá theo.`)) return;
    try {
      await api.del(`/v1/admin/providers/${p.id}`);
      await reload();
      notify('Đã xoá provider.');
    } catch (err) {
      notify('Lỗi xoá: ' + err.message, 'err');
    }
  };

  const B = { compatible: 'var(--success)', partial: 'var(--warning)', unknown: 'var(--text-dim)', incompatible: 'var(--danger)' };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
        <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700 }}>AI Providers</h3>
        <button onClick={() => openEdit()} style={{ ...btn('var(--gradient)', '#fff') }}>
          <Plus size={12} /> Thêm Provider
        </button>
      </div>

      <div style={{ display: 'grid', gap: '8px' }}>
        {providers.map((p) => (
          <div key={p.id} style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)', padding: '10px 12px',
            opacity: p.enabled ? 1 : 0.6,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{
                    width: '8px', height: '8px', borderRadius: '50%', flexShrink: 0,
                    background: p.enabled ? 'var(--success)' : 'var(--danger)',
                  }} title={p.enabled ? 'Đã bật' : 'Đang tắt'} />
                  <span style={{ fontWeight: 700, fontSize: 'var(--text-base)' }}>{p.name}</span>
                  <span style={{
                    fontSize: '10px', fontWeight: 600, padding: '1px 6px',
                    borderRadius: 'var(--radius-xs)', background: 'var(--info-light)', color: 'var(--info)',
                  }}>{p.kind}</span>
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginTop: '3px' }}>
                  <code style={{ background: 'var(--bg)', padding: '1px 5px', borderRadius: '3px' }}>{p.base_url}</code>
                  {' · '}<b style={{ color: 'var(--text)' }}>{p.models_count ?? 0} models</b>
                  {' · '}{fmtSynced(p.last_synced_at)}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center' }}>
                {/* Breakdown — bấm chip lọc tương ứng ở tab Models */}
                {['compatible', 'partial', 'unknown', 'incompatible'].map((k) => (
                  <button key={k} onClick={() => onViewModels(p.id, k)}
                    title={`Xem model ${k} của ${p.name}`}
                    style={{ ...btn('transparent', B[k]), border: '1px solid var(--border)' }}>
                    {k === 'compatible' ? '✓' : k === 'partial' ? '⚠' : k === 'unknown' ? '?' : '✕'} {p.breakdown?.[k] ?? 0}
                  </button>
                ))}
                <span style={{ borderLeft: '1px solid var(--border)', height: '20px', margin: '0 2px' }} />
                <button onClick={() => test(p.id, p.name)} style={btn('var(--info-light)', 'var(--info)')} title="Kiểm tra kết nối">
                  <SearchCheck size={11} /> Test
                </button>
                <button onClick={() => sync(p.id, p.name)} disabled={syncing === p.id}
                  style={btn('var(--primary-light)', 'var(--primary)')} title="Đồng bộ registry từ provider">
                  {syncing === p.id ? <LoaderCircle size={11} className="spin" /> : <RefreshCw size={11} />} Đồng bộ
                </button>
                <button onClick={() => onViewModels(p.id)} style={btn('var(--bg)', 'var(--text-dim)')}>
                  <Eye size={11} /> Xem models
                </button>
                <button onClick={() => openEdit(p)} style={btn('var(--accent-light)', 'var(--accent)')}>
                  <Pencil size={11} /> Sửa
                </button>
                <button onClick={() => toggle(p)} style={btn(p.enabled ? 'var(--bg)' : 'var(--success-light)', p.enabled ? 'var(--text-dim)' : 'var(--success)')}>
                  <Power size={11} /> {p.enabled ? 'Tắt' : 'Bật'}
                </button>
                <button onClick={() => remove(p)} style={btn('var(--danger-light)', 'var(--danger)')}>
                  <Trash2 size={11} />
                </button>
              </div>
            </div>
          </div>
        ))}
        {providers.length === 0 && (
          <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
            Chưa có provider — bấm "Thêm Provider" (ví dụ OpenRouter: <code>https://openrouter.ai/api/v1</code>).
          </div>
        )}
      </div>

      {/* Modal tạo/sửa — đủ field, hết window.prompt */}
      {editing && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 'var(--z-modal)' }}
          onClick={() => !loading && setEditing(null)}>
          <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius-lg)', padding: '16px', width: 'min(480px, 92vw)' }}
            onClick={(e) => e.stopPropagation()}>
            <h4 style={{ fontSize: 'var(--text-base)', fontWeight: 700, marginBottom: '12px' }}>
              {editing === 'NEW' ? 'Thêm Provider' : `Sửa provider: ${form.name}`}
            </h4>
            <div style={{ display: 'grid', gap: '10px' }}>
              <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>Tên
                <input style={{ ...input, marginTop: '4px' }} value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="OpenRouter" />
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '8px' }}>
                <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>Loại
                  <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}
                    style={{ ...input, marginTop: '4px' }}>
                    <option value="openai">openai (chuẩn OpenAI-compatible)</option>
                    <option value="ollama">ollama</option>
                  </select>
                </label>
                <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>Base URL
                  <input style={{ ...input, marginTop: '4px' }} value={form.base_url}
                    onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                    placeholder="https://openrouter.ai/api/v1" />
                </label>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                  API Key {editing !== 'NEW' && '(để trống = giữ key cũ)'}
                  <input type="password" style={{ ...input, marginTop: '4px' }} value={form.api_key || ''}
                    onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                    placeholder={editing !== 'NEW' ? '••••••••' : 'sk-or-v1-...'} />
                </label>
                <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>Prefix ID (tuỳ chọn)
                  <input style={{ ...input, marginTop: '4px' }} value={form.prefix_id || ''}
                    onChange={(e) => setForm({ ...form, prefix_id: e.target.value })} />
                </label>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '14px' }}>
              <button onClick={() => setEditing(null)} style={btn('var(--bg)', 'var(--text-dim)')}>Huỷ</button>
              <button onClick={save} disabled={loading} style={{ ...btn('var(--gradient)', '#fff'), opacity: loading ? 0.6 : 1 }}>
                Lưu
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
