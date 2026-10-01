import { useRef, useState } from 'react';
import { Download, Upload } from 'lucide-react';
import { Card, SectionTitle, btnStyle, errStyle, okStyle } from './parts.jsx';

// Xuất / nhập cấu hình (scope Hệ thống) — GET/POST /v1/admin/config/*.
// File export KHÔNG BAO GIỜ chứa secret (đã assert bằng test backend) — chỉ
// nhớ TÊN khóa secret để nhập vào hệ mới không quên.
export default function ConfigImportExport() {
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);

  const exportConfig = async () => {
    setMsg(null); setErr(null);
    try {
      const res = await fetch('/v1/admin/config/export', { credentials: 'include' });
      if (!res.ok) { setErr((await res.json()).detail || 'Không xuất được.'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `voicevibe-config-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setMsg('Đã tải file cấu hình JSON (không chứa khóa bí mật).');
    } catch (e) { setErr(e.message); }
  };

  const importConfig = async (text) => {
    setMsg(null); setErr(null);
    setBusy(true);
    try {
      let body;
      try {
        body = JSON.parse(text);
      } catch {
        setErr('File không phải JSON hợp lệ.');
        return;
      }
      const res = await fetch('/v1/admin/config/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(body),
      });
      const d = await res.json();
      if (res.ok) {
        const { imported, warnings } = d;
        setMsg(`Đã nhập: ${imported.settings} setting, ${imported.providers} provider, `
          + `${imported.stages} công đoạn, ${imported.prompts} prompt.`
          + (warnings?.length ? ` Cảnh báo: ${warnings.join(' · ')}` : ''));
      } else {
        setErr(d.detail || 'Nhập thất bại.');
      }
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };

  const onFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => importConfig(String(reader.result || ''));
    reader.readAsText(f);
    e.target.value = '';
  };

  return (
    <div>
      <SectionTitle title="Xuất / nhập cấu hình" badge="system"
        desc="đem cấu hình (providers, công đoạn, prompt, settings) giữa hai hệ VoiceVibe" />
      <Card title="Xuất cấu hình JSON">
        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', margin: '0 0 10px' }}>
          File gồm: settings không bí mật (khóa bí mật chỉ là TÊN nhắc nhập tay),
          providers (KHÔNG kèm api_key), công đoạn → model, prompt hệ thống.
        </p>
        <button onClick={exportConfig} style={{ ...btnStyle, display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
          <Download size={14} /> Tải file cấu hình
        </button>
      </Card>
      <Card title="Nhập cấu hình">
        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', margin: '0 0 10px' }}>
          Nhập an toàn: provider khớp theo TÊN (cập nhật, không tạo trùng, KHÔNG đụng
          api_key đã có), nhập bao nhiêu lần cũng cho cùng kết quả. Provider/công đoạn
          thiếu sẽ được báo ở phần cảnh báo, không làm chết cả file.
        </p>
        <input ref={fileRef} type="file" accept="application/json,.json" onChange={onFile}
          style={{ fontSize: 'var(--text-sm)', color: 'var(--text)', marginBottom: '8px', display: 'block' }} />
        <button onClick={() => fileRef.current?.click()} disabled={busy}
          style={{ ...btnStyle, display: 'inline-flex', alignItems: 'center', gap: '6px', opacity: busy ? 0.6 : 1 }}>
          <Upload size={14} /> {busy ? 'Đang nhập…' : 'Chọn file JSON để nhập'}
        </button>
        {msg && <div style={{ ...okStyle, marginTop: '8px' }}>{msg}</div>}
        {err && <div style={{ ...errStyle, marginTop: '8px' }}>{err}</div>}
      </Card>
    </div>
  );
}
