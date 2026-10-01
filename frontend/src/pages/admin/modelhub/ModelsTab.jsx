import { useState, useEffect, useCallback } from 'react';
import { Search, Power, Info, LoaderCircle, ChevronDown, ChevronRight } from 'lucide-react';
import CompatBadge from './CompatBadge.jsx';

// 18 capability + nhãn — khớp app/capabilities.py (backend là nguồn sự thật,
// đây chỉ là nhãn hiển thị; số lượng phải khớp, test CI không soi file này).
const CAPS = [
  ['text', 'Văn bản'], ['chat', 'Chat'], ['reasoning', 'Suy luận'], ['vision', 'Thị giác'],
  ['imageGeneration', 'Sinh ảnh'], ['imageUnderstanding', 'Hiểu ảnh'],
  ['audioInput', 'Nhận audio'], ['audioOutput', 'Xuất audio'],
  ['speechToText', 'STT'], ['textToSpeech', 'TTS'], ['translation', 'Dịch thuật'],
  ['videoInput', 'Nhận video'], ['videoGeneration', 'Sinh video'],
  ['embeddings', 'Vector nhúng'], ['reranking', 'Xếp hạng'],
  ['functionCalling', 'Gọi hàm'], ['structuredOutput', 'Cấu trúc'], ['streaming', 'Streaming'],
];
const COMPS = ['compatible', 'partial', 'unknown', 'incompatible'];

const input = {
  padding: '6px 9px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)',
  fontSize: 'var(--text-xs)', background: 'var(--bg)', color: 'var(--text)',
};
const btn = (bg, color) => ({
  background: bg, color, border: 'none', padding: '4px 9px', borderRadius: 'var(--radius-xs)',
  fontSize: 'var(--text-xs)', fontWeight: 600, cursor: 'pointer',
  display: 'inline-flex', alignItems: 'center', gap: '4px', whiteSpace: 'nowrap',
});

const fmtNum = (n) => (n == null ? '' : n >= 1000000 ? `${(n / 1e6).toFixed(0)}M` : n >= 1000 ? `${(n / 1000).toFixed(0)}K` : String(n));

function CapChip({ value, children }) {
  // Chỉ vẽ khi TRUE — list view cần gọn; giá trị False/None xem ở modal chi tiết.
  if (value !== true) return null;
  return (
    <span style={{
      fontSize: '10px', fontWeight: 600, padding: '1px 6px', borderRadius: 'var(--radius-xs)',
      background: 'var(--bg)', color: 'var(--text-dim)', border: '1px solid var(--border)',
    }}>{children}</span>
  );
}

export default function ModelsTab({ api, notify, initial = {}, loading, setLoading }) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [breakdown, setBreakdown] = useState(null);
  const [providers, setProviders] = useState({});
  const [limit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [detail, setDetail] = useState(null);
  const [collapsed, setCollapsed] = useState({});
  // filter state — khởi tạo từ initial khi "Xem models" của ProvidersTab gọi
  const [q, setQ] = useState(initial.q || '');
  const [providerId, setProviderId] = useState(initial.provider_id || '');
  const [comp, setComp] = useState(initial.compatibility || '');
  const [cap, setCap] = useState('');
  const [enabled, setEnabled] = useState('');

  useEffect(() => {
    setQ(initial.q || '');
    setProviderId(initial.provider_id || '');
    setComp(initial.compatibility || '');
    setOffset(0);
  }, [initial.provider_id, initial.compatibility, initial.q, initial.nonce]);

  const load = useCallback(async (off, append) => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ limit: String(limit), offset: String(off) });
      if (q) qs.set('q', q);
      if (providerId) qs.set('provider_id', providerId);
      if (comp) qs.set('compatibility', comp);
      if (cap) qs.set('capability', cap);
      if (enabled) qs.set('enabled', enabled);
      const d = await api.get(`/v1/admin/models?${qs}`);
      setRows((prev) => (append ? [...prev, ...(d.items || [])] : d.items || []));
      setTotal(d.total || 0);
      setBreakdown(d.breakdown || null);
      setProviders(d.providers || {});
    } catch (err) {
      notify('Lỗi tải models: ' + err.message, 'err');
    } finally {
      setLoading(false);
    }
  }, [api, q, providerId, comp, cap, enabled, limit]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(0, false); }, [load]);

  const toggle = async (m) => {
    try {
      const updated = await api.patch(`/v1/admin/models/${m.id}`, { body: { enabled: !m.enabled } });
      setRows(rows.map((r) => (r.id === m.id ? { ...r, enabled: updated.enabled } : r)));
      if (detail?.id === m.id) setDetail({ ...detail, enabled: updated.enabled });
    } catch (err) {
      notify('Lỗi: ' + err.message, 'err');
    }
  };

  // Nhóm theo provider → org (yêu cầu: model được nhóm theo provider; org con
  // trong provider — OpenRouter: openai/anthropic/google...)
  const groups = [];
  for (const m of rows) {
    const pk = m.provider_id || '?';
    let g = groups.find((x) => x.provider_id === pk);
    if (!g) { g = { provider_id: pk, name: m.provider_name || pk, orgs: [] }; groups.push(g); }
    let o = g.orgs.find((x) => x.name === (m.org || '—'));
    if (!o) { o = { name: m.org || '—', items: [] }; g.orgs.push(o); }
    o.items.push(m);
  }

  return (
    <div>
      {/* Filter bar */}
      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '10px' }}>
        <div style={{ position: 'relative' }}>
          <Search size={12} style={{ position: 'absolute', left: '8px', top: '50%', transform: 'translateY(-50%)', opacity: 0.5 }} />
          <input placeholder="Tìm model…" value={q} onChange={(e) => { setQ(e.target.value); }}
            style={{ ...input, paddingLeft: '24px', width: '170px' }}
            onKeyDown={(e) => e.key === 'Enter' && load(0, false)} />
        </div>
        <select value={providerId} onChange={(e) => setProviderId(e.target.value)} style={input}>
          <option value="">Mọi provider</option>
          {Object.entries(providers).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
        </select>
        <select value={comp} onChange={(e) => setComp(e.target.value)} style={input}>
          <option value="">Mọi tương thích</option>
          <option value="compatible">✓ Compatible</option>
          <option value="partial">⚠ Một phần</option>
          <option value="unknown">? Không rõ</option>
          <option value="incompatible">✕ Không tương thích</option>
        </select>
        <select value={cap} onChange={(e) => setCap(e.target.value)} style={input}>
          <option value="">Mọi capability</option>
          {CAPS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
        <select value={enabled} onChange={(e) => setEnabled(e.target.value)} style={input}>
          <option value="">Bật + Tắt</option>
          <option value="true">Đã bật</option>
          <option value="false">Đã tắt</option>
        </select>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginLeft: 'auto' }}>
          <b style={{ color: 'var(--text)' }}>{total}</b> model
          {breakdown && <>
            {' · '}<span style={{ color: 'var(--success)' }}>✓{breakdown.compatible}</span>
            {' '}<span style={{ color: 'var(--warning)' }}>⚠{breakdown.partial}</span>
            {' '}<span>？{breakdown.unknown}</span>
            {' '}<span style={{ color: 'var(--danger)' }}>✕{breakdown.incompatible}</span>
          </>}
        </span>
      </div>

      {/* Danh sách NHÓM theo provider → org — không bao giờ render "model1, model2, ..." */}
      {groups.map((g) => (
        <div key={g.provider_id} style={{ marginBottom: '10px' }}>
          {groups.length > 1 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '4px 2px', fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text)' }}>
              <button onClick={() => setCollapsed({ ...collapsed, [g.provider_id]: !collapsed[g.provider_id] })}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-dim)', padding: '2px' }}>
                {collapsed[g.provider_id] ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
              </button>
              {g.name}
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', fontWeight: 400 }}>
                — {g.orgs.reduce((a, o) => a + o.items.length, 0)} models
              </span>
            </div>
          )}
          {!collapsed[g.provider_id] && g.orgs.filter((o) => o.name !== '—' || g.orgs.length > 1 ? true : true).map((o) => (
            <div key={o.name} style={{ marginBottom: '4px' }}>
              {g.orgs.length > 1 && o.name !== '—' && (
                <div style={{ fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-muted)', margin: '4px 0 3px 14px' }}>{o.name}</div>
              )}
              <div style={{ display: 'grid', gap: '5px' }}>
                {o.items.map((m) => (
                  <div key={m.id} style={{
                    background: 'var(--surface)', border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)', padding: '7px 10px',
                    display: 'flex', alignItems: 'center', gap: '8px',
                    opacity: m.enabled ? 1 : 0.55,
                  }}>
                    <CompatBadge status={m.compatibility?.status} small />
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {m.display_name || m.model_id}
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)', marginLeft: '6px' }}>
                          {m.model_id}
                        </span>
                      </div>
                      <div style={{ display: 'flex', gap: '4px', marginTop: '3px', flexWrap: 'wrap' }}>
                        {CAPS.map(([k, label]) => (
                          <CapChip key={k} value={(m.capabilities || {})[k]}>{label}</CapChip>
                        ))}
                        {m.context_window && <CapChip value={true}>ctx {fmtNum(m.context_window)}</CapChip>}
                      </div>
                    </div>
                    <span style={{
                      fontSize: '9px', fontWeight: 700, padding: '2px 6px', borderRadius: 'var(--radius-xs)',
                      background: m.enabled ? 'var(--success-light)' : 'var(--bg)',
                      color: m.enabled ? 'var(--success)' : 'var(--text-muted)', flexShrink: 0,
                    }}>{m.enabled ? 'ENABLED' : 'DISABLED'}</span>
                    <button onClick={() => toggle(m)} style={btn(m.enabled ? 'var(--bg)' : 'var(--success-light)', m.enabled ? 'var(--text-dim)' : 'var(--success)')}>
                      <Power size={11} /> {m.enabled ? 'Tắt' : 'Bật'}
                    </button>
                    <button onClick={() => setDetail(m)} style={btn('var(--primary-light)', 'var(--primary)')}>
                      <Info size={11} /> Chi tiết
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ))}

      {rows.length === 0 && !loading && (
        <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
          Chưa có model trong registry — bấm "Đồng bộ" ở tab Providers để pull từ nhà cung cấp.
        </div>
      )}

      {rows.length < total && (
        <div style={{ textAlign: 'center', marginTop: '8px' }}>
          <button onClick={() => { const o = offset + limit; setOffset(o); load(o, true); }}
            style={btn('var(--bg)', 'var(--text-dim)', )}>
            <LoaderCircle size={11} /> Hiện thêm ({rows.length}/{total})
          </button>
        </div>
      )}

      {/* Modal chi tiết */}
      {detail && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 'var(--z-modal)' }}
          onClick={() => setDetail(null)}>
          <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius-lg)', padding: '16px', width: 'min(680px, 94vw)', maxHeight: '86vh', overflowY: 'auto' }}
            className="scrollbar-thin" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '10px', marginBottom: '10px' }}>
              <div>
                <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700 }}>{detail.display_name || detail.model_id}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                  {detail.model_id} · {detail.provider_name}
                </div>
              </div>
              <CompatBadge status={detail.compatibility?.status} />
            </div>

            {detail.description && (
              <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '10px', lineHeight: 1.5 }}>{detail.description}</p>
            )}

            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '5px' }}>Capabilities</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '4px', marginBottom: '12px' }}>
              {CAPS.map(([k, label]) => {
                const v = (detail.capabilities || {})[k];
                const icon = v === true ? '✓' : v === false ? '✕' : '—';
                const color = v === true ? 'var(--success)' : v === false ? 'var(--danger)' : 'var(--text-muted)';
                return (
                  <div key={k} style={{ fontSize: 'var(--text-xs)', color, fontWeight: v !== null ? 600 : 400 }}>
                    {icon} {label}
                  </div>
                );
              })}
            </div>

            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '5px' }}>Chức năng hệ thống</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 16px', marginBottom: '12px' }}>
              {(detail.compatibility?.supported_features || []).map((f) => (
                <div key={f} style={{ fontSize: 'var(--text-xs)', color: 'var(--success)' }}>✓ {f}</div>
              ))}
              {(detail.compatibility?.partial_features || []).map((f) => (
                <div key={f} style={{ fontSize: 'var(--text-xs)', color: 'var(--warning)' }}>⚠ {f}</div>
              ))}
              {(detail.compatibility?.unsupported_features || []).map((f) => (
                <div key={f} style={{ fontSize: 'var(--text-xs)', color: 'var(--danger)' }}>✕ {f}</div>
              ))}
            </div>

            {(detail.compatibility?.reasons || []).length > 0 && (
              <div style={{ background: 'var(--bg)', borderRadius: 'var(--radius-sm)', padding: '8px 10px', fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginBottom: '12px' }}>
                {detail.compatibility.reasons.map((r, i) => <div key={i}>• {r}</div>)}
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginBottom: '10px' }}>
              <div>Context: <b style={{ color: 'var(--text)' }}>{detail.context_window ? fmtNum(detail.context_window) : '—'}</b></div>
              <div>Output limit: <b style={{ color: 'var(--text)' }}>{detail.output_token_limit ? fmtNum(detail.output_token_limit) : '—'}</b></div>
              <div>Pricing: <b style={{ color: 'var(--text)' }}>{detail.pricing ? `$${detail.pricing.input}/$${detail.pricing.output} per 1M tok` : '—'}</b></div>
              <div>Nguồn capability: <b style={{ color: 'var(--text)' }}>{detail.capability_source}</b></div>
              <div>Điểm: <b style={{ color: 'var(--text)' }}>{detail.compatibility?.score ?? 0}</b></div>
              <div>Đồng bộ: <b style={{ color: 'var(--text)' }}>{detail.last_synced_at ? new Date(detail.last_synced_at * 1000).toLocaleString('vi-VN') : '—'}</b></div>
            </div>

            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
              <button onClick={() => toggle(detail)} style={btn(detail.enabled ? 'var(--bg)' : 'var(--success-light)', detail.enabled ? 'var(--text-dim)' : 'var(--success)')}>
                <Power size={11} /> {detail.enabled ? 'Tắt model' : 'Bật model'}
              </button>
              <button onClick={() => setDetail(null)} style={btn('var(--primary-light)', 'var(--primary)')}>Đóng</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
