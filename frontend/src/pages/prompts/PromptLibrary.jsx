import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search, Plus, Pencil, Trash2, Eye, RefreshCw, Languages,
  ChevronDown, ChevronRight, Copy, X,
} from 'lucide-react';
import { useApi } from '../../hooks/useApi.jsx';

// Thư viện Prompt — prompt CÁ NHÂN theo user (khác Prompt hệ thống trong tab
// Prompts). Component dùng chung 2 nơi: trang /prompts (mọi user) + tab
// "Prompt của tôi" trong AI Model Hub (admin) — props `embedded` chỉ ẩn header.
//
// Giao diện (Compact UI): filter bar + list row card (tên + chips + hành động),
// modal tạo/sửa (textarea lớn + biến tự dò), modal chi tiết (content + Lịch sử
// phiên bản accordion + khôi phục). "Dùng cho dịch" → /translate-text với
// prompt đã chọn (localStorage vv_prompt_pick).

const btn = (bg, color) => ({
  background: bg, color, border: 'none', padding: '4px 9px', borderRadius: 'var(--radius-xs)',
  fontSize: 'var(--text-xs)', fontWeight: 600, cursor: 'pointer',
  display: 'inline-flex', alignItems: 'center', gap: '4px', whiteSpace: 'nowrap',
});
const input = {
  padding: '7px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)',
  fontSize: 'var(--text-sm)', background: 'var(--bg)', color: 'var(--text)', width: '100%',
};
const chip = {
  fontSize: '10px', fontWeight: 600, padding: '1px 6px', borderRadius: 'var(--radius-xs)',
  background: 'var(--bg)', color: 'var(--text-dim)', border: '1px solid var(--border)',
};
const fmtTime = (ts) => (ts ? new Date(ts * 1000).toLocaleString('vi-VN') : '—');
const VAR_RE = /\{(\w+)\}/g;

function scanVars(content) {
  const out = [];
  for (const m of (content || '').matchAll(VAR_RE)) {
    if (!out.includes(m[1])) out.push(m[1]);
  }
  return out;
}

export default function PromptLibrary({ embedded = false }) {
  const { api } = useApi();
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [limit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const [tags, setTags] = useState([]);          // gộp từ rows cho dropdown
  const [toast, setToast] = useState(null);
  // editing: {id?, name, description, tags, content, note} — modal tạo/sửa
  const [editing, setEditing] = useState(null);
  const [detail, setDetail] = useState(null);    // row đầy đủ (GET detail)
  const [historyOpen, setHistoryOpen] = useState(false);
  const [viewing, setViewing] = useState(null);  // {v, content} đang xem trong modal chi tiết

  const notify = useCallback((msg, cls = 'ok') => {
    setToast({ msg, cls });
    clearTimeout(window._plToast);
    window._plToast = setTimeout(() => setToast(null), 5000);
  }, []);

  const load = useCallback(async (off = 0, append = false) => {
    try {
      const qs = new URLSearchParams({ limit: String(limit), offset: String(off) });
      if (q) qs.set('q', q);
      if (tagFilter) qs.set('tag', tagFilter);
      const d = await api.get(`/v1/prompts?${qs}`);
      setRows((prev) => (append ? [...prev, ...(d.prompts || [])] : d.prompts || []));
      setTotal(d.total || 0);
      const tset = new Set();
      (append ? [...rows, ...(d.prompts || [])] : d.prompts || []).forEach((p) => (p.tags || []).forEach((t) => tset.add(t)));
      setTags([...tset].sort());
    } catch (err) {
      notify('Lỗi tải prompt: ' + err.message, 'err');
    }
  }, [api, q, tagFilter, limit]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(0, false); }, [load]);

  const openCreate = () => setEditing({ id: null, name: '', description: '', tags: '', content: '', note: '' });
  const openEdit = async (row) => {
    try {
      const d = await api.get(`/v1/prompts/${row.id}`);
      setEditing({ id: d.id, name: d.name, description: d.description || '', tags: (d.tags || []).join(', '), content: d.content, note: '' });
    } catch (err) {
      notify('Lỗi: ' + err.message, 'err');
    }
  };

  const save = async () => {
    if (!editing.name.trim() || !editing.content.trim()) {
      notify('Thiếu tên hoặc nội dung prompt.', 'err');
      return;
    }
    const tagList = editing.tags.split(',').map((t) => t.trim()).filter(Boolean);
    try {
      if (editing.id) {
        await api.put(`/v1/prompts/${editing.id}`, {
          body: { name: editing.name, content: editing.content, description: editing.description, tags: tagList, note: editing.note || undefined },
        });
        notify('Đã lưu — bản cũ được chụp vào Lịch sử phiên bản.');
      } else {
        await api.post('/v1/prompts', {
          body: { name: editing.name, content: editing.content, description: editing.description, tags: tagList },
        });
        notify('Đã tạo prompt.');
      }
      setEditing(null);
      load(0, false);
    } catch (err) {
      notify('Lỗi lưu: ' + err.message, 'err');
    }
  };

  const remove = async (row) => {
    if (!window.confirm(`Xoá prompt "${row.name}"? Lịch sử phiên bản cũng biến mất theo.`)) return;
    try {
      await api.del(`/v1/prompts/${row.id}`);
      notify('Đã xoá prompt.');
      load(0, false);
    } catch (err) {
      notify('Lỗi xoá: ' + err.message, 'err');
    }
  };

  const openDetail = async (row) => {
    try {
      const d = await api.get(`/v1/prompts/${row.id}`);
      setDetail(d);
      setViewing(null);
      setHistoryOpen(false);
    } catch (err) {
      notify('Lỗi: ' + err.message, 'err');
    }
  };

  const restore = async (entry) => {
    if (!window.confirm(`Khôi phục v${entry.v}? Bản hiện tại sẽ được chụp vào lịch sử.`)) return;
    try {
      const d = await api.post(`/v1/prompts/${detail.id}/restore`, { body: { version: entry.v } });
      setDetail(d);
      setViewing(null);
      notify(`Đã khôi phục v${entry.v}.`);
      load(0, false);
    } catch (err) {
      notify('Lỗi khôi phục: ' + err.message, 'err');
    }
  };

  const useForTranslate = (row) => {
    try { localStorage.setItem('vv_prompt_pick', row.id); } catch {}
    navigate('/translate-text');
  };

  const copy = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      notify('Đã sao chép nội dung prompt.');
    } catch {
      notify('Trình duyệt chặn sao chép — bôi đen và Ctrl+C giúp mình.', 'err');
    }
  };

  return (
    <div>
      {/* ---- Header (ẩn khi nhúng tab ModelHub) ---- */}
      {!embedded && (
        <div style={{ marginBottom: '14px' }}>
          <h1 style={{ fontSize: 'var(--text-4xl)', fontWeight: 700, marginBottom: '4px' }}>Prompt của tôi</h1>
          <p style={{ color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
            Prompt riêng của bạn — dùng cho job Dịch văn bản. Prompt hệ thống sửa ở AI Model Hub → Prompt hệ thống.
          </p>
        </div>
      )}
      {embedded && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '10px' }}>
          <p style={{ color: 'var(--text-dim)', fontSize: 'var(--text-xs)', margin: 0 }}>
            Prompt riêng của bạn — mọi user chỉ thấy prompt của mình.
          </p>
        </div>
      )}

      {/* ---- Filter bar + nút tạo ---- */}
      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '10px' }}>
        <div style={{ position: 'relative' }}>
          <Search size={12} style={{ position: 'absolute', left: '8px', top: '50%', transform: 'translateY(-50%)', opacity: 0.5 }} />
          <input placeholder="Tìm prompt…" value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && load(0, false)}
            style={{ ...input, paddingLeft: '24px', width: '170px', fontSize: 'var(--text-xs)', padding: '6px 9px 6px 24px' }} />
        </div>
        <select value={tagFilter} onChange={(e) => setTagFilter(e.target.value)}
          style={{ ...input, width: 'auto', fontSize: 'var(--text-xs)', padding: '6px 9px' }}>
          <option value="">Mọi tag</option>
          {tags.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginLeft: 'auto' }}>
          <b style={{ color: 'var(--text)' }}>{total}</b> prompt
        </span>
        <button onClick={openCreate} style={{ ...btn('var(--gradient)', '#fff') }}>
          <Plus size={12} /> Tạo prompt
        </button>
      </div>

      {/* ---- Danh sách ---- */}
      <div style={{ display: 'grid', gap: '5px' }}>
        {rows.map((p) => (
          <div key={p.id} style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)', padding: '7px 10px',
            display: 'flex', alignItems: 'center', gap: '8px',
          }}>
            <div style={{ minWidth: 0, flex: 1, cursor: 'pointer' }} onClick={() => openDetail(p)}>
              <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {p.name}
                {p.version > 1 && <span style={{ ...chip, marginLeft: '6px' }}>v{p.version}</span>}
              </div>
              {p.description && (
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {p.description}
                </div>
              )}
              <div style={{ display: 'flex', gap: '4px', marginTop: '3px', flexWrap: 'wrap' }}>
                {(p.tags || []).slice(0, 3).map((t) => <span key={t} style={chip}>{t}</span>)}
                {(p.tags || []).length > 3 && <span style={chip}>+{p.tags.length - 3}</span>}
                {(p.variables || []).map((v) => (
                  <span key={v} style={{ ...chip, fontFamily: 'var(--font-mono)' }}>{'{'}{v}{'}'}</span>
                ))}
                <span style={{ ...chip, border: 'none' }}>sửa {fmtTime(p.updated_at)}</span>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
              <button onClick={() => openDetail(p)} style={btn('var(--primary-light)', 'var(--primary)')}>
                <Eye size={11} /> Xem
              </button>
              <button onClick={() => openEdit(p)} style={btn('var(--bg)', 'var(--text-dim)')}>
                <Pencil size={11} /> Sửa
              </button>
              <button onClick={() => remove(p)} style={btn('var(--danger-light)', 'var(--danger)')}>
                <Trash2 size={11} />
              </button>
              <button onClick={() => useForTranslate(p)} style={btn('var(--success-light)', 'var(--success)')}>
                <Languages size={11} /> Dùng cho dịch
              </button>
            </div>
          </div>
        ))}
      </div>

      {rows.length === 0 && (
        <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
          Chưa có prompt nào — bấm "Tạo prompt" để thêm prompt riêng cho job Dịch
          (ví dụ: "Dịch ngắn gọn phong cách TikTok").
        </div>
      )}

      {rows.length < total && (
        <div style={{ textAlign: 'center', marginTop: '8px' }}>
          <button onClick={() => { const o = offset + limit; setOffset(o); load(o, true); }}
            style={btn('var(--bg)', 'var(--text-dim)')}>
            Hiện thêm ({rows.length}/{total})
          </button>
        </div>
      )}

      {/* ---- Modal tạo/sửa ---- */}
      {editing && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 'var(--z-modal)' }}
          onClick={() => setEditing(null)}>
          <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius-lg)', padding: '16px', width: 'min(680px, 94vw)', maxHeight: '86vh', overflowY: 'auto' }}
            className="scrollbar-thin" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <h4 style={{ fontSize: 'var(--text-base)', fontWeight: 700, margin: 0 }}>
                {editing.id ? `Sửa prompt: ${editing.name}` : 'Tạo prompt mới'}
              </h4>
              <button onClick={() => setEditing(null)} style={{ ...btn('transparent', 'var(--text-dim)') }}><X size={14} /></button>
            </div>
            <div style={{ display: 'grid', gap: '10px' }}>
              <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>Tên prompt (bắt buộc)
                <input style={{ ...input, marginTop: '4px' }} value={editing.name}
                  onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                  placeholder="VD: Dịch phụ đề TikTok ngắn gọn" />
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>Mô tả (tuỳ chọn)
                  <input style={{ ...input, marginTop: '4px' }} value={editing.description}
                    onChange={(e) => setEditing({ ...editing, description: e.target.value })} />
                </label>
                <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>Tags (cách nhau bằng dấu phẩy)
                  <input style={{ ...input, marginTop: '4px' }} value={editing.tags}
                    onChange={(e) => setEditing({ ...editing, tags: e.target.value })}
                    placeholder="tiktok, ngắn gọn" />
                </label>
              </div>
              {editing.id && (
                <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>Ghi chú phiên bản (tuỳ chọn)
                  <input style={{ ...input, marginTop: '4px' }} value={editing.note}
                    onChange={(e) => setEditing({ ...editing, note: e.target.value })}
                    placeholder="VD: đổi giọng thân thiện hơn" />
                </label>
              )}
              <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                Nội dung prompt {editing.id && '— lưu sẽ chụp bản hiện tại vào Lịch sử phiên bản'}
                <textarea style={{ ...input, marginTop: '4px', fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', resize: 'vertical' }}
                  rows={12} value={editing.content}
                  onChange={(e) => setEditing({ ...editing, content: e.target.value })}
                  placeholder={'You are a professional translator. Translate from {source} to {target}...'} />
              </label>
              <div>
                <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '4px' }}>
                  Biến tự dò
                </div>
                <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                  {scanVars(editing.content).map((v) => (
                    <span key={v} style={{ ...chip, fontFamily: 'var(--font-mono)' }}>{'{'}{v}{'}'}</span>
                  ))}
                  {scanVars(editing.content).length === 0 && (
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>chưa có — dùng {'{source}'}, {'{target}'} cho cặp ngôn ngữ</span>
                  )}
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: '5px' }}>
                  {'{source}'}, {'{target}'} được điền theo cặp ngôn ngữ chọn lúc dịch. {'{text}'} KHÔNG dùng được — nội dung cần dịch nằm ở message gửi model.
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '12px' }}>
              <button onClick={() => setEditing(null)} style={btn('var(--bg)', 'var(--text-dim)')}>Huỷ</button>
              <button onClick={save} style={btn('var(--gradient)', '#fff')}>Lưu</button>
            </div>
          </div>
        </div>
      )}

      {/* ---- Modal chi tiết ---- */}
      {detail && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 'var(--z-modal)' }}
          onClick={() => setDetail(null)}>
          <div style={{ background: 'var(--surface)', borderRadius: 'var(--radius-lg)', padding: '16px', width: 'min(680px, 94vw)', maxHeight: '86vh', overflowY: 'auto' }}
            className="scrollbar-thin" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700 }}>{detail.name}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                  v{detail.version} · tạo {fmtTime(detail.created_at)} · sửa {fmtTime(detail.updated_at)}
                </div>
              </div>
              <button onClick={() => setDetail(null)} style={{ ...btn('transparent', 'var(--text-dim)') }}><X size={14} /></button>
            </div>
            <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', margin: '8px 0' }}>
              {(detail.tags || []).map((t) => <span key={t} style={chip}>{t}</span>)}
              {(detail.variables || []).map((v) => (
                <span key={v} style={{ ...chip, fontFamily: 'var(--font-mono)' }}>{'{'}{v}{'}'}</span>
              ))}
            </div>

            {viewing && (
              <div style={{ background: 'var(--info-light)', color: 'var(--info)', fontSize: 'var(--text-xs)', fontWeight: 600, padding: '5px 9px', borderRadius: 'var(--radius-xs)', marginBottom: '6px' }}>
                Đang xem v{viewing.v} (chỉ đọc) — Lưu/Khôi phục mới đổi bản hiện tại.
              </div>
            )}
            <div style={{ position: 'relative' }}>
              <pre style={{
                background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
                padding: '8px 10px', fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)',
                lineHeight: 1.5, overflowX: 'auto', maxHeight: '40vh', overflowY: 'auto', margin: 0,
                whiteSpace: 'pre-wrap',
              }} className="scrollbar-thin">{viewing ? viewing.content : detail.content}</pre>
              <button onClick={() => copy(viewing ? viewing.content : detail.content)}
                style={{ ...btn('var(--surface)', 'var(--text-dim)'), position: 'absolute', top: '6px', right: '6px', border: '1px solid var(--border)' }}>
                <Copy size={11} /> Sao chép
              </button>
            </div>

            {/* Lịch sử phiên bản — accordion */}
            <button onClick={() => setHistoryOpen(!historyOpen)}
              style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'none', border: 'none', cursor: 'pointer', padding: '10px 0 4px', color: 'var(--text)', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              {historyOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              Lịch sử phiên bản ({(detail.history || []).length})
            </button>
            {historyOpen && (
              <div style={{ display: 'grid', gap: '4px' }}>
                {(detail.history || []).map((h) => (
                  <div key={h.v} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '5px 8px', background: 'var(--bg)', borderRadius: 'var(--radius-xs)' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', fontWeight: 700 }}>v{h.v}</span>
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {h.note ? `${h.note} · ` : ''}{fmtTime(h.updated_at)}
                    </span>
                    <button onClick={() => setViewing({ v: h.v, content: h.content })} style={btn('var(--surface)', 'var(--text-dim)')}>
                      <Eye size={11} /> Xem
                    </button>
                    <button onClick={() => restore(h)} style={btn('var(--warning-light)', 'var(--warning)')}>
                      <RefreshCw size={11} /> Khôi phục
                    </button>
                  </div>
                ))}
                {(detail.history || []).length === 0 && (
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', padding: '4px 8px' }}>
                    Chưa có — lịch sử bắt đầu từ lần lưu thứ hai.
                  </div>
                )}
              </div>
            )}

            <div style={{ display: 'flex', gap: '6px', justifyContent: 'flex-end', marginTop: '12px', flexWrap: 'wrap' }}>
              <button onClick={() => { setDetail(null); openEdit(detail); }} style={btn('var(--bg)', 'var(--text-dim)')}>
                <Pencil size={11} /> Sửa
              </button>
              <button onClick={() => { setDetail(null); useForTranslate(detail); }} style={btn('var(--success-light)', 'var(--success)')}>
                <Languages size={11} /> Dùng cho dịch
              </button>
              <button onClick={() => { setDetail(null); remove(detail); }} style={btn('var(--danger-light)', 'var(--danger)')}>
                <Trash2 size={11} /> Xoá
              </button>
              <button onClick={() => setDetail(null)} style={btn('var(--primary-light)', 'var(--primary)')}>Đóng</button>
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div style={{
          position: 'fixed', bottom: '20px', left: '50%', transform: 'translateX(-50%)',
          background: 'var(--surface)', border: `1px solid ${toast.cls === 'err' ? 'var(--danger)' : 'var(--success)'}`,
          color: toast.cls === 'err' ? 'var(--danger)' : 'var(--success)',
          padding: '8px 16px', borderRadius: 'var(--radius)', fontSize: 'var(--text-sm)',
          fontWeight: 600, zIndex: 'var(--z-toast)', maxWidth: '90vw', boxShadow: 'var(--shadow-md)',
        }}>
          {toast.msg}
        </div>
      )}
    </div>
  );
}
