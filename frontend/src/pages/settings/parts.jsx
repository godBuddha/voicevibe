// Phần dùng chung của Settings Hub: nhãn scope, hàng "Sắp có", tiêu đề section.
// COMPACT UI: mọi màu/kích thước qua token var(--*) — không hex cứng (quy ước
// test_theme áp cho UI inline; SPA cũng giữ để đồng bộ).

// Nhãn scope nhỏ: cho người dùng biết setting này tác động ở tầm nào.
// Cá nhân = chỉ mình user; Hệ thống = toàn bộ instance self-hosted.
export function ScopeBadge({ scope }) {
  const personal = scope === 'personal';
  return (
    <span style={{
      fontSize: '10px', fontWeight: 700, letterSpacing: '0.03em',
      padding: '1px 6px', borderRadius: 'var(--radius-full)',
      background: personal ? 'var(--info-light)' : 'var(--primary-light)',
      color: personal ? 'var(--info)' : 'var(--primary)',
      whiteSpace: 'nowrap',
    }}>
      {personal ? 'Cá nhân' : 'Hệ thống'}
    </span>
  );
}

// Hàng mục "Sắp có" — spec quy định mục CHƯA CÓ NỀN TẢNG vẫn phải hiện để lộ
// lộ trình, nhưng không bấm được (không có menu chết: click KHÔNG điều hướng).
export function SoonRow({ label, icon: Icon, note }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '8px',
      padding: '6px 8px', borderRadius: 'var(--radius-sm)',
      color: 'var(--text-muted)', opacity: 0.65, cursor: 'not-allowed',
      fontSize: 'var(--text-sm)',
    }} title="Sắp có — phase sau">
      {Icon && <Icon size={14} style={{ flexShrink: 0 }} />}
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
        {label}
      </span>
      <span style={{
        fontSize: '10px', fontWeight: 600, padding: '1px 6px',
        borderRadius: 'var(--radius-full)', background: 'var(--chip)',
        color: 'var(--text-muted)', whiteSpace: 'nowrap',
      }}>
        Sắp có
      </span>
      {note}
    </div>
  );
}

// Tiêu đề section + mô tả 1 dòng — mỗi section mở bằng cái này.
export function SectionTitle({ title, desc, badge }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
      <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--text)', margin: 0 }}>
        {title}
      </h2>
      {badge && <ScopeBadge scope={badge} />}
      {desc && (
        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          — {desc}
        </span>
      )}
    </div>
  );
}

// Thẻ card chuẩn: nền surface, viền mảnh, padding nén 12px (Compact UI).
export function Card({ title, children, right }) {
  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)', padding: '12px', marginBottom: '12px',
    }}>
      {(title || right) && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, margin: 0, color: 'var(--text)' }}>
            {title}
          </h3>
          {right}
        </div>
      )}
      {children}
    </div>
  );
}

// Input + nhãn xếp dọc gọn — dùng lặp lại ở Profile/Security/Webhooks.
export function Field({ label, hint, children }) {
  return (
    <label style={{ display: 'block', marginBottom: '10px' }}>
      <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text)', marginBottom: '4px' }}>
        {label}
      </div>
      {children}
      {hint && (
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginTop: '4px' }}>
          {hint}
        </div>
      )}
    </label>
  );
}

export const inputStyle = {
  width: '100%', maxWidth: '420px', padding: '7px 10px',
  borderRadius: 'var(--radius)', border: '1px solid var(--border)',
  background: 'var(--bg)', color: 'var(--text)', fontSize: 'var(--text-sm)',
  fontFamily: 'inherit', boxSizing: 'border-box',
};

export const btnStyle = {
  background: 'var(--gradient)', color: '#fff', border: 'none',
  padding: '7px 14px', borderRadius: 'var(--radius)',
  fontSize: 'var(--text-sm)', fontWeight: 600, cursor: 'pointer',
};

export const errStyle = {
  padding: '8px 10px', borderRadius: 'var(--radius)',
  background: 'var(--danger-light)', color: 'var(--danger)',
  fontSize: 'var(--text-sm)', whiteSpace: 'pre-wrap',
};

export const okStyle = {
  padding: '8px 10px', borderRadius: 'var(--radius)',
  background: 'var(--success-light)', color: 'var(--success)',
  fontSize: 'var(--text-sm)',
};
