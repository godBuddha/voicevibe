import { useState } from 'react';

// Prompts tab — trích nguyên logic của ModelHub cũ (PUT /prompts/{key} +
// POST .../reset), không đổi hành vi nào.
const btn = (bg, color) => ({
  background: bg, color, border: 'none', padding: '4px 9px', borderRadius: 'var(--radius-xs)',
  fontSize: 'var(--text-xs)', fontWeight: 600, cursor: 'pointer',
});

export default function PromptsTab({ prompts, api, notify, reload }) {
  const [editing, setEditing] = useState(null);

  const save = async () => {
    try {
      await api.put(`/v1/admin/prompts/${editing.task_key}`, {
        body: { content: editing.content ?? editing.template ?? '' },
      });
      setEditing(null);
      await reload();
      notify('Đã lưu prompt.');
    } catch (err) {
      notify('Lỗi khi lưu prompt: ' + err.message, 'err');
    }
  };

  const reset = async (taskKey) => {
    if (!window.confirm('Reset về prompt mặc định?')) return;
    try {
      await api.post(`/v1/admin/prompts/${taskKey}/reset`);
      await reload();
      notify('Đã khôi phục mặc định.');
    } catch (err) {
      notify('Lỗi khi reset prompt: ' + err.message, 'err');
    }
  };

  return (
    <div>
      <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, marginBottom: '10px' }}>Prompt Templates</h3>
      <div style={{ display: 'grid', gap: '8px' }}>
        {prompts.map((p) => (
          <div key={p.task_key} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '10px 12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 700, textTransform: 'capitalize' }}>
                {p.task_key}
                {p.is_default === false && (
                  <span style={{ fontSize: '9px', color: 'var(--warning)', marginLeft: '6px', fontWeight: 400 }}>(đã sửa)</span>
                )}
              </h4>
              <div style={{ display: 'flex', gap: '6px' }}>
                <button onClick={() => reset(p.task_key)} style={btn('var(--warning-light)', 'var(--warning)')}>Reset mặc định</button>
                <button onClick={() => setEditing({ ...p })} style={btn('var(--primary-light)', 'var(--primary)')}>Sửa</button>
              </div>
            </div>
            {editing?.task_key === p.task_key ? (
              <div>
                <textarea
                  value={editing.content ?? editing.template ?? ''}
                  onChange={(e) => setEditing({ ...editing, content: e.target.value })}
                  rows={4}
                  style={{
                    width: '100%', padding: '8px 10px', borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border)', fontSize: 'var(--text-sm)',
                    fontFamily: 'var(--font-mono)', background: 'var(--bg)', color: 'var(--text)', resize: 'vertical',
                  }}
                />
                <div style={{ display: 'flex', gap: '8px', marginTop: '8px', justifyContent: 'flex-end' }}>
                  <button onClick={() => setEditing(null)} style={btn('var(--bg)', 'var(--text-dim)')}>Huỷ</button>
                  <button onClick={save} style={btn('var(--gradient)', '#fff')}>Lưu</button>
                </div>
              </div>
            ) : (
              <pre style={{
                background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
                padding: '8px 10px', fontSize: 'var(--text-xs)', color: 'var(--text)',
                lineHeight: 1.5, overflowX: 'auto', margin: 0,
              }}>{p.content || p.template}</pre>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
