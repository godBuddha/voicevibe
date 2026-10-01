import { Card, Field, SectionTitle, inputStyle, btnStyle, errStyle, okStyle } from './parts.jsx';

// Webhooks (scope Hệ thống): khóa ký HMAC cho callback job hoàn thành.
// Reuse setting `webhook.secret` hiện có — pipeline tasks._notify đã ký sẵn
// header X-VoiceVibe-Signature = HMAC-SHA256(secret, body JSON).
export default function Webhooks() {
  const [secret, setSecret] = useState('');
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);

  const save = async () => {
    setMsg(null); setErr(null);
    if (!secret.trim()) { setErr('Nhập giá trị MỚI — ô để trống nghĩa là giữ nguyên.'); return; }
    try {
      const res = await fetch('/v1/admin/settings/webhook.secret', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ value: secret.trim(), is_secret: true }),
      });
      const d = await res.json();
      if (res.ok) { setMsg('Đã lưu webhook.secret.'); setSecret(''); }
      else setErr(d.detail || 'Không lưu được.');
    } catch (e) { setErr(e.message); }
  };

  return (
    <div>
      <SectionTitle title="Webhooks" badge="system"
        desc="báo job hoàn thành về server của bạn — có chữ ký chống giả mạo" />
      <Card title="Khóa ký (webhook.secret)">
        <Field label="Giá trị mới"
          hint="Bất kỳ chuỗi ngẫu nhiên nào (ví dụ: openssl rand -hex 32). Job có webhook_url khi tạo sẽ POST kết quả về URL của bạn kèm header X-VoiceVibe-Signature = HMAC-SHA256(khóa, phần thân JSON). Server của bạn tính lại chữ ký để biết thông báo THẬT từ VoiceVibe.">
          <input type="password" value={secret} style={inputStyle}
            onChange={(e) => setSecret(e.target.value)}
            placeholder="Nhập giá trị MỚI (để trống = giữ nguyên)" autoComplete="new-password" />
        </Field>
        <button onClick={save} style={btnStyle}>Lưu khóa</button>
        {msg && <div style={{ ...okStyle, marginTop: '8px' }}>{msg}</div>}
        {err && <div style={{ ...errStyle, marginTop: '8px' }}>{err}</div>}
      </Card>
      <Card title="Cách kiểm tra nhanh">
        <ol style={{ fontSize: 'var(--text-sm)', color: 'var(--text)', margin: 0, paddingLeft: '18px' }}>
          <li style={{ marginBottom: '6px' }}>Lưu khóa ở trên.</li>
          <li style={{ marginBottom: '6px' }}>Dựng một URL nhận POST (ví dụ webhook.site hoặc server nội bộ).</li>
          <li style={{ marginBottom: '6px' }}>Tạo job bất kỳ với <code>webhook_url</code> trỏ tới URL đó.</li>
          <li>Ở server nhận: tính <code>HMAC-SHA256(khóa, body)</code> và so với header
            {' '}<code>X-VoiceVibe-Signature</code> — khớp là thông báo thật.</li>
        </ol>
      </Card>
    </div>
  );
}
