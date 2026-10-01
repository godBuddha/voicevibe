import { Eye } from 'lucide-react';

// Feature registry — chỉ HIỂN THỊ registry của backend (GET /v1/admin/features),
// không hard-code lại danh sách chức năng ở đây. Nút "Xem models" → tab Models
// với filter feature tương ứng.
const btn = {
  background: 'var(--primary-light)', color: 'var(--primary)', border: 'none',
  padding: '4px 9px', borderRadius: 'var(--radius-xs)', fontSize: 'var(--text-xs)',
  fontWeight: 600, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '4px',
};

export default function FeaturesTab({ features, onViewModels }) {
  return (
    <div>
      <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, marginBottom: '4px' }}>Chức năng hệ thống</h3>
      <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginBottom: '10px' }}>
        Registry chức năng của VoiceVibe — hệ thống tự đối chiếu capability model với từng chức năng để đánh dấu tương thích.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '8px' }}>
        {features.map((f) => (
          <div key={f.key} style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)', padding: '10px 12px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '6px' }}>
              <div style={{ fontWeight: 700, fontSize: 'var(--text-sm)' }}>{f.label}</div>
              {f.stage && (
                <span style={{ fontSize: '9px', fontWeight: 600, padding: '1px 6px', borderRadius: 'var(--radius-xs)', background: 'var(--info-light)', color: 'var(--info)' }}>
                  stage: {f.stage}
                </span>
              )}
            </div>
            {f.local_engine ? (
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: '6px' }}>
                ⚙ Engine local (VieNeu) — không chọn model cloud cho chức năng này.
              </div>
            ) : (
              <>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginTop: '5px' }}>
                  Bắt buộc:{' '}
                  {f.required.map((c, i) => (
                    <span key={c}>
                      {i > 0 && ', '}
                      <code style={{ background: 'var(--bg)', padding: '0 4px', borderRadius: '3px' }}>{c}</code>
                    </span>
                  ))}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '8px' }}>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--success)', fontWeight: 600 }}>✓ {f.models_compatible} tương thích</span>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--warning)', fontWeight: 600 }}>⚠ {f.models_partial} một phần</span>
                  <button onClick={() => onViewModels(f.key)} style={{ ...btn, marginLeft: 'auto' }}>
                    <Eye size={11} /> Xem models
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
