import { useEffect } from 'react';
import { Navigate, NavLink, useParams } from 'react-router-dom';
import {
  Bell, Boxes, Braces, Building2, Database, Download, FileClock, Fingerprint,
  KeyRound, Lock, MonitorCog, ScrollText, Settings as SettingsIcon,
  ShieldCheck, UserRound, UsersRound,
} from 'lucide-react';
import { useAuth } from '../../hooks/useAuth.jsx';
import AdminUsers from '../admin/Users.jsx';
import AdminModelHub from '../admin/ModelHub.jsx';
import AdminSettings from '../admin/Settings.jsx';
import ApiKeys from '../ApiKeys.jsx';
import Profile from './Profile.jsx';
import Appearance from './Appearance.jsx';
import Notifications from './Notifications.jsx';
import SessionsTab from './SessionsTab.jsx';
import SystemOverview from './SystemOverview.jsx';
import SecurityAuth from './SecurityAuth.jsx';
import Webhooks from './Webhooks.jsx';
import AuditLog from './AuditLog.jsx';
import JobsOverview from './JobsOverview.jsx';
import ConfigImportExport from './ConfigImportExport.jsx';
import FeatureFlags from './FeatureFlags.jsx';
import { BackupDocs, DangerZone } from './DocsCards.jsx';
import { SoonRow, ScopeBadge } from './parts.jsx';

// Cấu trúc thông tin Settings Hub — 8 nhóm theo SCOPE, mỗi mục gắn nhãn
// Cá nhân (chỉ user này) / Hệ thống (toàn bộ instance self-hosted).
//   adminOnly  : nhóm ẩn với user thường (server vẫn 403 — guard 2 lớp)
//   soon: true : mục CHƯA có nền tảng backend — hiện disabled "Sắp có",
//                KHÔNG điều hướng (không menu chết)
//   docs: true : card hướng dẫn vận hành (sao lưu/vùng nguy hiểm), không API
const GROUPS = [
  {
    key: 'personal', label: 'CÁ NHÂN', scope: 'personal', adminOnly: false,
    items: [
      ['profile', 'Hồ sơ', UserRound],
      ['appearance', 'Giao diện', SettingsIcon],
      ['notifications', 'Thông báo', Bell],
      ['sessions', 'Phiên đăng nhập', MonitorCog],
    ],
  },
  {
    key: 'ai', label: 'AI PLATFORM', scope: 'system', adminOnly: true,
    items: [
      ['ai-platform', 'AI Model Hub', Boxes],
    ],
  },
  {
    key: 'workspace', label: 'WORKSPACE', scope: 'system', adminOnly: true,
    items: [
      ['members', 'Thành viên', UsersRound],
      ['teams', 'Teams', Building2, 'soon'],
      ['roles', 'Vai trò & quyền', Fingerprint, 'soon'],
      ['shared', 'Tài nguyên dùng chung', Boxes, 'soon'],
      ['defaults', 'Workspace mặc định', Database, 'soon'],
    ],
  },
  {
    key: 'developer', label: 'DEVELOPER', scope: 'personal', adminOnly: false,
    items: [
      ['api-keys', 'API Keys', KeyRound],
      ['webhooks', 'Webhooks', Braces],
    ],
  },
  {
    key: 'security', label: 'BẢO MẬT', scope: 'system', adminOnly: true,
    items: [
      ['authentication', 'Xác thực', ShieldCheck],
      ['sso', 'SSO / OIDC', Lock, 'soon'],
      ['ldap', 'LDAP', Lock, 'soon'],
      ['mfa', 'Xác thực 2 lớp (MFA)', Lock, 'soon'],
    ],
  },
  {
    key: 'system', label: 'HỆ THỐNG', scope: 'system', adminOnly: true,
    items: [
      ['system', 'Tổng quan', MonitorCog],
      ['config', 'Cấu hình chung', SettingsIcon],
    ],
  },
  {
    key: 'observability', label: 'QUAN SÁT', scope: 'system', adminOnly: true,
    items: [
      ['audit', 'Nhật ký kiểm toán', ScrollText],
      ['jobs-overview', 'Tổng quan jobs', FileClock],
      ['ai-requests', 'AI requests / logs', Braces, 'soon'],
    ],
  },
  {
    key: 'advanced', label: 'NÂNG CAO', scope: 'system', adminOnly: true,
    items: [
      ['flags', 'Công tắc tính năng', SettingsIcon],
      ['import-export', 'Xuất / nhập cấu hình', Download],
      ['backup', 'Sao lưu & phục hồi', Database, 'docs'],
      ['danger', 'Vùng nguy hiểm', Database, 'docs'],
    ],
  },
];

const SECTION_COMPONENTS = {
  'profile': Profile,
  'appearance': Appearance,
  'notifications': Notifications,
  'sessions': SessionsTab,
  'ai-platform': AdminModelHub,
  'members': AdminUsers,
  'api-keys': ApiKeys,
  'webhooks': Webhooks,
  'authentication': SecurityAuth,
  'system': SystemOverview,
  'config': AdminSettings,
  'audit': AuditLog,
  'jobs-overview': JobsOverview,
  'import-export': ConfigImportExport,
  'flags': FeatureFlags,
  'backup': BackupDocs,
  'danger': DangerZone,
};

// Section nào NHÚNG component cũ (đã có h1 + padding riêng) → bỏ h1/padding
// qua prop embedded, đúng như hai lớp đã thống nhất.
const EMBEDDED_SECTIONS = new Set(['ai-platform', 'members', 'config', 'api-keys']);

const itemStyle = (active, soon) => ({
  display: 'flex',
  alignItems: 'center',
  gap: '8px',
  padding: '6px 8px',
  borderRadius: 'var(--radius-sm)',
  color: active ? 'var(--primary)' : 'var(--text-dim)',
  background: active ? 'var(--primary-light)' : 'transparent',
  textDecoration: 'none',
  transition: 'all 0.15s',
  fontSize: 'var(--text-sm)',
  fontWeight: active ? 600 : 400,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  marginBottom: '2px',
  cursor: soon ? 'not-allowed' : 'pointer',
  opacity: soon ? 0.65 : 1,
});

const headingStyle = {
  fontSize: '10px',
  fontWeight: 600,
  letterSpacing: '0.04em',
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  margin: '10px 8px 4px',
  display: 'flex',
  alignItems: 'center',
  gap: '6px',
};

export default function SettingsHub() {
  const { user, loading } = useAuth();
  const params = useParams();
  const isAdmin = user?.role === 'admin';
  const section = params.section || 'profile';

  // CHỜ PROFILE tải xong trước khi quyết redirect — user thường vào section
  // admin-only phải về hồ sơ, NHƯNG nếu quyết khi user chưa tải (null) thì cả
  // admin cũng bị đá về /settings/profile (lỗi thật lần chạy đầu audit: mọi
  // /settings/members|ai-platform|config|audit đều hạ cánh về Hồ sơ).
  if (loading) return null;

  // user thường truy cập URL admin-only → về hồ sơ (guard mềm; server vẫn 403
  // với mọi API admin — guard này chỉ để UI không hiện lỗi trống).
  const group = GROUPS.find((g) => g.items.some(([key]) => key === section));
  if (!group || (group.adminOnly && !isAdmin)) {
    return <Navigate to="/settings/profile" replace />;
  }

  const Component = SECTION_COMPONENTS[section];
  const meta = group.items.find(([key]) => key === section);
  const isSoon = meta?.[3] === 'soon';
  const isDocs = meta?.[3] === 'docs';
  const embedded = EMBEDDED_SECTIONS.has(section);

  // Đồng bộ URL khi vào /settings (không có section) — giữ nguyên lịch sử gọn.
  useEffect(() => {}, [section]);

  return (
    <div style={{ display: 'flex', gap: '16px', padding: '14px', maxWidth: '1400px', margin: '0 auto', width: '100%' }}>
      {/* Sidebar Settings riêng — phân nhóm theo scope, nhãn Cá nhân/Hệ thống */}
      <aside className="scrollbar-thin" style={{
        width: '212px', minWidth: '212px', position: 'sticky', top: '10px',
        alignSelf: 'flex-start', maxHeight: 'calc(100vh - 90px)', overflow: 'auto',
        borderRight: '1px solid var(--border)', paddingRight: '8px',
      }}>
        {GROUPS.filter((g) => !g.adminOnly || isAdmin).map((g) => (
          <div key={g.key}>
            <h4 style={headingStyle}>
              {g.label}
              <ScopeBadge scope={g.scope} />
            </h4>
            {g.items.map(([key, label, Icon, tag]) => (
              tag === 'soon' ? (
                <SoonRow key={key} label={label} icon={Icon} />
              ) : (
                <NavLink key={key} to={`/settings/${key}`} style={({ isActive }) => itemStyle(isActive, false)}>
                  <Icon size={14} strokeWidth={2} style={{ flexShrink: 0, opacity: 0.75 }} />
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
                </NavLink>
              )
            ))}
          </div>
        ))}
      </aside>

      <div style={{ flex: 1, minWidth: 0 }}>
        {isSoon ? (
          <div style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)', padding: '20px',
          }}>
            <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, margin: '0 0 6px' }}>
              {meta[1]}
            </h2>
            <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', margin: 0 }}>
              Sắp có — mục này nằm trong lộ trình nhưng chưa có nền tảng trong phiên
              hiện tại. Không cấu hình được và cũng KHÔNG ảnh hưởng hệ thống.
            </p>
          </div>
        ) : isDocs ? (
          <Component />
        ) : embedded ? (
          <Component embedded />
        ) : (
          <Component />
        )}
      </div>
    </div>
  );
}
