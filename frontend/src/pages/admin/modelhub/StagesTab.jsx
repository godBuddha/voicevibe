import { useState, useEffect } from 'react';
import { Power } from 'lucide-react';
import CompatBadge from './CompatBadge.jsx';

const btn = (bg, color) => ({
  background: bg, color, border: 'none', padding: '4px 9px', borderRadius: 'var(--radius-xs)',
  fontSize: 'var(--text-xs)', fontWeight: 600, cursor: 'pointer',
  display: 'inline-flex', alignItems: 'center', gap: '4px', whiteSpace: 'nowrap',
});
const input = {
  padding: '6px 9px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)',
  fontSize: 'var(--text-xs)', background: 'var(--bg)', color: 'var(--text)', width: '100%',
};

// Model selector cho stage editor: nhóm Recommended (rule hệ thống — GET
// /features/{key}/models đã sort supported trước) / Compatible / Partial;
// incompatible + unknown ẨN mặc định, có [Hiện tất cả].
function ModelPicker({ api, stage, providerId, value, onChange }) {
  const [options, setOptions] = useState(null);
  const [showAll, setShowAll] = useState(false);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const feature = STAGE_FEATURES[stage];

  // Fetch khi mở dropdown; đổi provider/showAll → xoá cache rồi fetch lại.
  // (useEffect, KHÔNG gọi trong render — StrictMode render đôi sẽ fetch đôi.)
  useEffect(() => {
    if (!open) return;
    if (!providerId) { setOptions(null); return; }
    setLoading(true);
    const qs = new URLSearchParams({ provider_id: providerId, enabled: 'true', limit: '200' });
    if (feature && !showAll) qs.set('feature', feature);
    api.get(`/v1/admin/models?${qs}`)
      .then((d) => setOptions(d.items || []))
      .catch(() => setOptions([]))
      .finally(() => setLoading(false));
  }, [open, providerId, showAll, feature]); // eslint-disable-line react-hooks/exhaustive-deps

  const groups = {
    recommended: (options || []).filter((m) => feature && (m.compatibility?.supported_features || []).includes(feature)).slice(0, 8),
    compatible: (options || []).filter((m) => !(feature && (m.compatibility?.supported_features || []).includes(feature))
      && m.compatibility?.status === 'compatible'),
    partial: (options || []).filter((m) => m.compatibility?.status === 'partial'),
    other: showAll ? (options || []).filter((m) => !['compatible', 'partial'].includes(m.compatibility?.status)) : [],
  };

  return (
    <div style={{ position: 'relative', minWidth: 0 }}>
      <input readOnly value={value ? value.model_id : ''} placeholder={providerId ? '— chọn model —' : 'chọn provider trước'}
        onFocus={() => setOpen(true)}
        onClick={() => setOpen(true)}
        style={{ ...input, cursor: 'pointer', fontFamily: value ? 'var(--font-mono)' : 'inherit' }} />
      {open && providerId && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 20, marginTop: '4px',
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)', maxHeight: '260px', overflowY: 'auto', padding: '4px',
        }} className="scrollbar-thin">
          {loading && <div style={{ padding: '8px', fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>Đang tải…</div>}
          {!loading && options?.length === 0 && (
            <div style={{ padding: '8px', fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
              Chưa có model — bấm "Đồng bộ" ở tab Providers.
            </div>
          )}
          {groups.recommended.length > 0 && (
            <>
              <div style={{ fontSize: '9px', fontWeight: 700, color: 'var(--success)', textTransform: 'uppercase', padding: '4px 6px 2px' }}>
                ✓ Đề xuất cho "{feature}"
              </div>
              {groups.recommended.map((m) => <PickRow key={m.id} m={m} onPick={() => { onChange(m); setOpen(false); }} />)}
            </>
          )}
          {groups.compatible.length > 0 && (
            <>
              <div style={{ fontSize: '9px', fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', padding: '4px 6px 2px' }}>
                Compatible
              </div>
              {groups.compatible.map((m) => <PickRow key={m.id} m={m} onPick={() => { onChange(m); setOpen(false); }} />)}
            </>
          )}
          {groups.partial.length > 0 && (
            <>
              <div style={{ fontSize: '9px', fontWeight: 700, color: 'var(--warning)', textTransform: 'uppercase', padding: '4px 6px 2px' }}>
                ⚠ Một phần
              </div>
              {groups.partial.map((m) => <PickRow key={m.id} m={m} onPick={() => { onChange(m); setOpen(false); }} />)}
            </>
          )}
          {groups.other.length > 0 && (
            <>
              <div style={{ fontSize: '9px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', padding: '4px 6px 2px' }}>
                ✕ Không tương thích / ?
              </div>
              {groups.other.map((m) => <PickRow key={m.id} m={m} onPick={() => { onChange(m); setOpen(false); }} />)}
            </>
          )}
          <button onClick={() => setShowAll(!showAll)}
            style={{ ...btn('transparent', 'var(--primary)'), width: '100%', justifyContent: 'center', marginTop: '4px' }}>
            {showAll ? 'Ẩn model không tương thích' : 'Hiện tất cả model'}
          </button>
          <button onClick={() => setOpen(false)}
            style={{ ...btn('transparent', 'var(--text-dim)'), width: '100%', justifyContent: 'center' }}>
            Đóng
          </button>
        </div>
      )}
    </div>
  );
}

function PickRow({ m, onPick }) {
  return (
    <button onClick={onPick} style={{
      display: 'flex', alignItems: 'center', gap: '6px', width: '100%', textAlign: 'left',
      padding: '5px 6px', background: 'none', border: 'none', cursor: 'pointer',
      borderRadius: 'var(--radius-xs)',
    }}
      onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg)'; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'none'; }}>
      <CompatBadge status={m.compatibility?.status} small />
      <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
        {m.display_name || m.model_id}
      </span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--text-muted)' }}>{m.model_id}</span>
    </button>
  );
}

// map stage → feature — giữ khớp STAGE_FEATURES của backend (app/capabilities.py)
const STAGE_FEATURES = {
  stt: 'speech_to_text', translate: 'text_translation', retranslate: 'text_translation',
  tts: 'text_to_speech', dub: 'video_translation', subtitle: 'subtitle_translation',
};
const STAGE_NOTES = {
  stt: 'Có model cloud → job STT gọi provider đó; không có → faster-whisper local.',
  tts: 'Cloud TTS chỉ hỗ trợ giọng PRESET — giọng CLONE (voice profile) luôn chạy local.',
  translate: 'Model chat của provider được dùng để dịch qua prompt. Fallback theo thứ tự.',
  retranslate: 'Dùng để dịch lại ngắn hơn khi timing không khớp — cùng feature với translate.',
  dub: 'Pipeline lồng tiếng chạy engine local; model cloud của công đoạn này phục vụ dịch.',
  subtitle: 'Dịch nội dung phụ đề qua model chat.',
};

export default function StagesTab({ stages, providers, api, notify, reload, loading, setLoading }) {
  const [editing, setEditing] = useState(null); // {stage, provider_id, model_id, order}

  const save = async () => {
    if (editing.provider_id && !editing.model_id) {
      notify('Chọn model trước khi lưu (hoặc chọn "Auto" để bỏ gán).', 'err');
      return;
    }
    setLoading(true);
    try {
      // Auto = bỏ gán hẳn (provider_id null): runtime bỏ qua row model rỗng,
      // nên "Auto" phải là KHÔNG CÓ row — rõ nghĩa hơn là row ẩn.
      await api.put(`/v1/admin/stages/${editing.stage}`, {
        body: {
          provider_id: editing.provider_id || null,
          model: editing.model_id || '',
          params: {}, order: editing.order,
        },
      });
      setEditing(null);
      await reload();
      notify('Đã lưu công đoạn.');
    } catch (err) {
      notify('Lỗi: ' + err.message, 'err');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, marginBottom: '10px' }}>Các công đoạn xử lý</h3>
      {editing && (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '12px', marginBottom: '10px' }}>
          <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 700, marginBottom: '8px' }}>
            Gán model cho công đoạn: <code>{editing.stage}</code> {editing.order > 0 && <span style={{ color: 'var(--warning)' }}>(fallback #{editing.order})</span>}
          </h4>
          <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: '8px' }}>
            <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>Provider
              <select value={editing.provider_id || ''} style={{ ...input, marginTop: '4px' }}
                onChange={(e) => setEditing({ ...editing, provider_id: e.target.value || null, model_id: '' })}>
                <option value="">(Auto — engine local mặc định)</option>
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>{p.name} {p.enabled ? '' : '(đang tắt)'}</option>
                ))}
              </select>
            </label>
            <label style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
              Model {STAGE_FEATURES[editing.stage] && <>— lọc theo chức năng <b style={{ color: 'var(--text)' }}>{STAGE_FEATURES[editing.stage]}</b></>}
              <ModelPicker api={api} stage={editing.stage} providerId={editing.provider_id}
                value={editing.model_id ? { model_id: editing.model_id } : null}
                onChange={(m) => setEditing({ ...editing, model_id: m.model_id })} />
            </label>
          </div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginTop: '6px' }}>
            💡 {STAGE_NOTES[editing.stage]}
          </div>
          <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '10px' }}>
            <button onClick={() => setEditing(null)} style={btn('var(--bg)', 'var(--text-dim)')}>Huỷ</button>
            <button onClick={save} disabled={loading} style={{ ...btn('var(--gradient)', '#fff'), opacity: loading ? 0.6 : 1 }}>Lưu</button>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gap: '8px' }}>
        {stages.map((sg) => (
          <div key={sg.stage} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '10px 12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, textTransform: 'capitalize' }}>
                  {sg.stage}
                  {STAGE_FEATURES[sg.stage] && (
                    <span style={{ fontSize: '9px', color: 'var(--text-muted)', marginLeft: '6px', fontWeight: 400 }}>
                      chức năng: {STAGE_FEATURES[sg.stage]}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginTop: '2px' }}>
                  {sg.models.length > 0
                    ? `Chính: ${sg.models.join(', ')}`
                    : '— Auto (engine local / cấu hình mặc định)'}
                </div>
                {(sg.fallback || []).length > 0 && (
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginTop: '2px' }}>
                    Fallback: {sg.fallback.join(' → ')}
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', gap: '6px' }}>
                <button onClick={() => setEditing({
                  stage: sg.stage, order: 0,
                  provider_id: (sg.items.find((x) => x.order === 0) || {}).provider_id || null,
                  model_id: (sg.items.find((x) => x.order === 0) || {}).model || '',
                })} style={btn('var(--primary-light)', 'var(--primary)')}>
                  <Power size={11} /> Gán chính
                </button>
                <button onClick={() => setEditing({
                  stage: sg.stage, order: (Math.max(0, ...sg.items.map((x) => x.order)) || 0) + 1,
                  provider_id: null, model_id: '',
                })} style={btn('var(--warning-light)', 'var(--warning)')}>
                  + Fallback
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
