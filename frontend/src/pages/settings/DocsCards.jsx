import { Link } from 'react-router-dom';
import { TriangleAlert } from 'lucide-react';
import { Card, SectionTitle, btnStyle } from './parts.jsx';

// Sao lưu & phục hồi (scope Hệ thống) — CARD HƯỚNG DẪN, không API.
// Lý do: backup đụng tới volume/postgres dump — làm bằng lệnh vận hành trên
// server là đúng chỗ, không chèn endpoint chạy shell vào API (rủi ro không đáng).
function Code({ children }) {
  return (
    <code style={{
      display: 'block', background: 'var(--code-bg)', color: 'var(--text)',
      padding: '7px 10px', borderRadius: 'var(--radius)', fontSize: 'var(--text-xs)',
      fontFamily: 'ui-monospace, monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
      marginBottom: '8px',
    }}>
      {children}
    </code>
  );
}

export function BackupDocs() {
  return (
    <div>
      <SectionTitle title="Sao lưu & phục hồi" badge="system"
        desc="3 thứ cần sao lưu: database, media, file cấu hình" />
      <Card title="Sao lưu toàn bộ">
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text)', margin: '0 0 8px' }}>
          Cần chụp 3 nhóm: (1) database — tài khoản, phiên, settings, provider, model registry,
          lịch sử job; (2) thư mục media — file audio/video/phụ đề kết quả; (3) file
          <code> .env</code> + cấu hình compose (từ đó có <code>SETTINGS_MASTER_KEY</code> —
          MẤT KHÓA NÀY = KHÔNG GIẢI MÃ ĐƯỢC secret cũ).
        </p>
        <Code>{'# 1. Database (Postgres trong compose):'}
          {'docker compose exec postgres pg_dump -U voicevibe voicevibe > backup-db.sql'}
          {'#    (SQLite: sqlite3 /đường/dến/voicevibe.db ".backup backup.db")'}</Code>
        <Code>{'# 2. Thư mục media:'}
          {'docker run --rm -v voicevibe_media:/data -v $PWD:/out alpine \\'}
          {'  tar czf /out/media-backup.tar.gz -C /data .'}</Code>
        <Code>{'# 3. Cấu hình + env (chứa SETTINGS_MASTER_KEY):'}
          {'cp deploy/.env backup-env.txt  # và cất ở nơi an toàn'}</Code>
      </Card>
      <Card title="Phục hồi">
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text)', margin: '0 0 8px' }}>
          Khôi phục theo thứ tự ngược: dựng lại stack từ compose + <code>.env</code>
          {' '}(đúng <code>SETTINGS_MASTER_KEY</code> cũ) → nạp <code>backup-db.sql</code>
          {' '}→ trả media về volume. Khởi động app: mọi bảng thiếu sẽ tự được tạo
          (migration tự chạy khi khởi động), dữ liệu cũ giữ nguyên.
        </p>
        <Code>{'docker compose exec -T postgres psql -U voicevibe voicevibe < backup-db.sql'}</Code>
        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', margin: 0 }}>
          Lưu ý: khôi phục PHIÊN BẢN app mới hơn lên DB cũ là an toàn (cột mới tự thêm);
          hạ phiên bản app cũ hơn trên DB mới có thể mất cột — tránh.
        </p>
      </Card>
    </div>
  );
}

export function DangerZone() {
  return (
    <div>
      <SectionTitle title="Vùng nguy hiểm" badge="system"
        desc="hành động không thể hoàn tác — đặt dưới cùng cho phải suy nghĩ trước khi bấm" />
      <div style={{
        border: '1px solid var(--danger)', borderRadius: 'var(--radius-lg)',
        padding: '12px', background: 'var(--surface)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
          <TriangleAlert size={15} style={{ color: 'var(--danger)' }} />
          <b style={{ color: 'var(--danger)', fontSize: 'var(--text-base)' }}>
            Không có nút "xoá toàn bộ hệ thống" — cố ý
          </b>
        </div>
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text)', margin: '0 0 10px' }}>
          Một endpoint xoá sạch dữ liệu là một lần lỡ tay của chính quản trị viên.
          Self-host thì xoá hệ thống = xoá container + volume (lệnh vận hành, có thời gian
          suy nghĩ lại). Mọi hành động "nguy hiểm nhưng CẦN" đã có chỗ an toàn riêng:
        </p>
        <ul style={{ fontSize: 'var(--text-sm)', color: 'var(--text)', margin: '0 0 12px', paddingLeft: '18px' }}>
          <li style={{ marginBottom: '4px' }}>Khoá tài khoản ai đó → <Link to="/settings/members" style={{ color: 'var(--primary)' }}>Trang Thành viên</Link> → Khoá</li>
          <li style={{ marginBottom: '4px' }}>Đặt lại mật khẩu ai đó → Trang Thành viên → Đặt lại mật khẩu (tự đăng xuất mọi phiên của họ)</li>
          <li style={{ marginBottom: '4px' }}>Gỡ provider (kèm model registry của nó) → <Link to="/settings/ai-platform" style={{ color: 'var(--primary)' }}>AI Model Hub</Link> → Providers</li>
          <li style={{ marginBottom: '4px' }}>Xoá job + file kết quả → Lịch sử Jobs → Xoá</li>
        </ul>
        <Link to="/settings/members">
          <button style={btnStyle}>Mở Trang Thành viên</button>
        </Link>
      </div>
    </div>
  );
}
