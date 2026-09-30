import { useState, useEffect } from 'react';
import { useApi } from '../../hooks/useApi.jsx';

export default function AdminUsers() {
  const { api } = useApi();
  const [users, setUsers] = useState([]);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newUser, setNewUser] = useState({ email: '', password: '', role: 'user' });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchUsers();
  }, [api]);

  const fetchUsers = async () => {
    try {
      // Backend trả {users: [{user_id, email, role, is_active, ...}]} —
      // trang đọc {id, status}. Chuyển tại đây, một điểm duy nhất.
      const data = await api.get('/v1/admin/users');
      setUsers((data.users || []).map(u => ({
        ...u,
        id: u.user_id,
        status: u.is_active ? 'active' : 'suspended',
      })));
    } catch {}
  };

  const createUser = async () => {
    if (!newUser.email || !newUser.password) return;
    setLoading(true);
    try {
      // Backend CreateUserIn bắt buộc password (tối thiểu theo chính sách) —
      // bản mock không cần nên form đầu tiên thiếu ô này, đã thêm.
      await api.post('/v1/admin/users', {
        body: {
          email: newUser.email,
          password: newUser.password,
          role: newUser.role,
        },
      });
      const data = await api.get('/v1/admin/users');
      setUsers((data.users || []).map(u => ({
        ...u, id: u.user_id, status: u.is_active ? 'active' : 'suspended',
      })));
      setShowCreateModal(false);
      setNewUser({ email: '', password: '', role: 'user' });
    } catch (err) {
      alert('Lỗi khi tạo user: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const resetPassword = async (id) => {
    // Backend ResetPasswordIn nhận mật khẩu MỚI do admin cung cấp (trả về số
    // phiên bị đá), không sinh "mật khẩu tạm" như bản mock tưởng.
    const pw = prompt('Nhập mật khẩu mới cho user này:');
    if (!pw) return;
    try {
      const res = await api.post(`/v1/admin/users/${id}/reset-password`, { body: { password: pw } });
      alert(`Đã đổi mật khẩu — ${res.sessions_revoked} phiên cũ bị đá ra.`);
    } catch (err) {
      alert('Lỗi khi reset mật khẩu: ' + err.message);
    }
  };

  const toggleStatus = async (id, active) => {
    try {
      await api.post(`/v1/admin/users/${id}/${active ? 'activate' : 'deactivate'}`, {});
      setUsers(users.map(u => u.id === id ? { ...u, status: active ? 'active' : 'suspended' } : u));
    } catch (err) {
      alert('Lỗi khi thay đổi trạng thái: ' + err.message);
    }
  };

  return (
    <div style={{ padding: '20px', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <div>
          <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '8px', fontWeight: 700 }}>
            Quản lý Users
          </h1>
          <p style={{ color: 'var(--text-dim)' }}>
            Thêm, sửa, xoá và quản lý tài khoản người dùng
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          style={{
            background: 'var(--gradient)',
            color: '#fff',
            border: 'none',
            padding: '10px 14px',
            borderRadius: 'var(--radius)',
            fontSize: 'var(--text-base)',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          + Tạo User
        </button>
      </div>

      {/* Create user modal */}
      {showCreateModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 'var(--z-modal)',
        }}
        onClick={() => !loading && setShowCreateModal(false)}
        >
          <div
            style={{
              background: 'var(--surface)',
              borderRadius: 'var(--radius-lg)',
              padding: '16px',
              maxWidth: '400px',
              width: '90%',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, marginBottom: '14px' }}>
              Tạo User mới
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '8px', fontWeight: 600 }}>
                  Email
                </label>
                <input
                  type="email"
                  value={newUser.email}
                  onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '10px 10px',
                    borderRadius: 'var(--radius)',
                    border: '1px solid var(--border)',
                    fontSize: 'var(--text-base)',
                    background: 'var(--bg)',
                    color: 'var(--text)',
                  }}
                  required
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '8px', fontWeight: 600 }}>
                  Mật khẩu
                </label>
                <input
                  type="password"
                  value={newUser.password}
                  onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                  placeholder="Tối thiểu 8 ký tự"
                  style={{
                    width: '100%',
                    padding: '10px 10px',
                    borderRadius: 'var(--radius)',
                    border: '1px solid var(--border)',
                    fontSize: 'var(--text-base)',
                    background: 'var(--bg)',
                    color: 'var(--text)',
                  }}
                  required
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '8px', fontWeight: 600 }}>
                  Vai trò
                </label>
                <select
                  value={newUser.role}
                  onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '10px 10px',
                    borderRadius: 'var(--radius)',
                    border: '1px solid var(--border)',
                    fontSize: 'var(--text-base)',
                    background: 'var(--bg)',
                    color: 'var(--text)',
                  }}
                >
                  <option value="user">User</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '10px', marginTop: '14px' }}>
              <button
                onClick={createUser}
                disabled={!newUser.email || !newUser.password || loading}
                style={{
                  flex: 1,
                  background: 'var(--gradient)',
                  color: '#fff',
                  border: 'none',
                  padding: '10px 12px',
                  borderRadius: 'var(--radius)',
                  fontWeight: 600,
                  cursor: loading ? 'not-allowed' : 'pointer',
                  opacity: loading ? 0.6 : 1,
                }}
              >
                {loading ? 'Đang tạo...' : 'Tạo'}
              </button>
              <button
                onClick={() => {
                  if (!loading) {
                    setShowCreateModal(false);
                    setNewUser({ email: '', role: 'user' });
                  }
                }}
                style={{
                  background: 'var(--bg)',
                  color: 'var(--text-dim)',
                  border: '1px solid var(--border)',
                  padding: '10px 12px',
                  borderRadius: 'var(--radius)',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Huỷ
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Users table */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-base)' }}>
            <thead style={{ background: 'var(--bg)', borderBottom: '1px solid var(--border)' }}>
              <tr>
                <th style={{ padding: '12px', textAlign: 'left', fontWeight: 600, color: 'var(--text-dim)' }}>Email</th>
                <th style={{ padding: '12px', textAlign: 'left', fontWeight: 600, color: 'var(--text-dim)' }}>Vai trò</th>
                <th style={{ padding: '12px', textAlign: 'left', fontWeight: 600, color: 'var(--text-dim)' }}>Trạng thái</th>
                <th style={{ padding: '12px', textAlign: 'center', fontWeight: 600, color: 'var(--text-dim)' }}>Hành động</th>
              </tr>
            </thead>
            <tbody>
              {users.map(user => (
                <tr key={user.id} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '12px', color: 'var(--text)' }}>{user.email}</td>
                  <td style={{ padding: '12px' }}>
                    <span style={{
                      padding: '4px 10px',
                      borderRadius: 'var(--radius-xs)',
                      background: user.role === 'admin' ? 'var(--danger-light)' : 'var(--info-light)',
                      color: user.role === 'admin' ? 'var(--danger)' : 'var(--info)',
                      fontSize: 'var(--text-sm)',
                      fontWeight: 600,
                    }}>
                      {user.role === 'admin' ? 'Admin' : 'User'}
                    </span>
                  </td>
                  <td style={{ padding: '12px' }}>
                    <span style={{
                      padding: '4px 10px',
                      borderRadius: 'var(--radius-xs)',
                      background: user.status === 'active' ? 'var(--success-light)' : 'var(--danger-light)',
                      color: user.status === 'active' ? 'var(--success)' : 'var(--danger)',
                      fontSize: 'var(--text-sm)',
                      fontWeight: 600,
                    }}>
                      {user.status === 'active' ? 'Hoạt động' : 'Chặn'}
                    </span>
                  </td>
                  <td style={{ padding: '12px' }}>
                    <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', flexWrap: 'wrap' }}>
                      <button
                        onClick={() => resetPassword(user.id)}
                        style={{
                          background: 'var(--info-light)',
                          color: 'var(--info)',
                          border: 'none',
                          padding: '4px 8px',
                          borderRadius: 'var(--radius-xs)',
                          fontSize: 'var(--text-xs)',
                          cursor: 'pointer',
                        }}
                      >
                        Reset mật khẩu
                      </button>
                      <button
                        onClick={() => toggleStatus(user.id, user.status !== 'active')}
                        style={{
                          background: user.status === 'active' ? 'var(--danger-light)' : 'var(--success-light)',
                          color: user.status === 'active' ? 'var(--danger)' : 'var(--success)',
                          border: 'none',
                          padding: '4px 8px',
                          borderRadius: 'var(--radius-xs)',
                          fontSize: 'var(--text-xs)',
                          cursor: 'pointer',
                        }}
                      >
                        {user.status === 'active' ? 'Chặn' : 'Mở lại'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}