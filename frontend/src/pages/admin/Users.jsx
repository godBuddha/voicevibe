import { useState, useEffect } from 'react';
import { useApi } from '../../hooks/useApi.jsx';

export default function AdminUsers() {
  const { api } = useApi();
  const [users, setUsers] = useState([]);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newUser, setNewUser] = useState({ email: '', role: 'user', credits: 0 });
  const [selectedUser, setSelectedUser] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchUsers();
  }, [api]);

  const fetchUsers = async () => {
    try {
      const data = await api.get('/v1/admin/users');
      setUsers(data);
    } catch {}
  };

  const createUser = async () => {
    if (!newUser.email) return;
    setLoading(true);
    try {
      const res = await api.post('/v1/admin/users', { body: newUser });
      setUsers([...users, { ...res, ...newUser }]);
      setShowCreateModal(false);
      setNewUser({ email: '', role: 'user', credits: 0 });
    } catch (err) {
      alert('Lỗi khi tạo user: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const resetPassword = async (id) => {
    try {
      const res = await api.post(`/v1/admin/users/${id}/reset-password`);
      alert(`Mật khẩu tạm cho user: ${res.tempPassword}`);
    } catch (err) {
      alert('Lỗi khi reset mật khẩu: ' + err.message);
    }
  };

  const updateCredits = async (id, credits) => {
    try {
      await api.post(`/v1/admin/users/${id}/credits`, { body: { credits } });
      setUsers(users.map(u => u.id === id ? { ...u, credits } : u));
    } catch (err) {
      alert('Lỗi khi cập nhật credits: ' + err.message);
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

  const editUser = (user) => {
    setSelectedUser({ ...user, tempCredits: user.credits });
  };

  const saveEdit = () => {
    if (selectedUser.tempCredits !== selectedUser.credits) {
      updateCredits(selectedUser.id, selectedUser.tempCredits);
    }
    setSelectedUser(null);
  };

  return (
    <div style={{ padding: '40px', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
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
            padding: '12px 24px',
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
              padding: '32px',
              maxWidth: '400px',
              width: '90%',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, marginBottom: '24px' }}>
              Tạo User mới
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
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
                    padding: '10px 12px',
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
                    padding: '10px 12px',
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
              <div>
                <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '8px', fontWeight: 600 }}>
                  Credits ban đầu
                </label>
                <input
                  type="number"
                  value={newUser.credits}
                  onChange={(e) => setNewUser({ ...newUser, credits: parseInt(e.target.value) || 0 })}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    borderRadius: 'var(--radius)',
                    border: '1px solid var(--border)',
                    fontSize: 'var(--text-base)',
                    background: 'var(--bg)',
                    color: 'var(--text)',
                  }}
                  min={0}
                />
              </div>
            </div>
            <div style={{ display: 'flex', gap: '12px', marginTop: '24px' }}>
              <button
                onClick={createUser}
                disabled={!newUser.email || loading}
                style={{
                  flex: 1,
                  background: 'var(--gradient)',
                  color: '#fff',
                  border: 'none',
                  padding: '10px 20px',
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
                    setNewUser({ email: '', role: 'user', credits: 0 });
                  }
                }}
                style={{
                  background: 'var(--bg)',
                  color: 'var(--text-dim)',
                  border: '1px solid var(--border)',
                  padding: '10px 20px',
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
                <th style={{ padding: '16px', textAlign: 'left', fontWeight: 600, color: 'var(--text-dim)' }}>Email</th>
                <th style={{ padding: '16px', textAlign: 'left', fontWeight: 600, color: 'var(--text-dim)' }}>Vai trò</th>
                <th style={{ padding: '16px', textAlign: 'left', fontWeight: 600, color: 'var(--text-dim)' }}>Credits</th>
                <th style={{ padding: '16px', textAlign: 'left', fontWeight: 600, color: 'var(--text-dim)' }}>Trạng thái</th>
                <th style={{ padding: '16px', textAlign: 'center', fontWeight: 600, color: 'var(--text-dim)' }}>Hành động</th>
              </tr>
            </thead>
            <tbody>
              {users.map(user => (
                <tr key={user.id} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '16px', color: 'var(--text)' }}>{user.email}</td>
                  <td style={{ padding: '16px' }}>
                    <span style={{
                      padding: '4px 12px',
                      borderRadius: 'var(--radius-xs)',
                      background: user.role === 'admin' ? 'var(--danger-light)' : 'var(--info-light)',
                      color: user.role === 'admin' ? 'var(--danger)' : 'var(--info)',
                      fontSize: 'var(--text-sm)',
                      fontWeight: 600,
                    }}>
                      {user.role === 'admin' ? 'Admin' : 'User'}
                    </span>
                  </td>
                  <td style={{ padding: '16px' }}>
                    {selectedUser?.id === user.id ? (
                      <input
                        type="number"
                        value={selectedUser.tempCredits}
                        onChange={(e) => setSelectedUser({ ...selectedUser, tempCredits: parseInt(e.target.value) || 0 })}
                        style={{
                          padding: '4px 8px',
                          borderRadius: 'var(--radius-xs)',
                          border: '1px solid var(--border)',
                          width: '120px',
                        }}
                      />
                    ) : (
                      user.credits.toLocaleString('vi-VN')
                    )}
                  </td>
                  <td style={{ padding: '16px' }}>
                    <span style={{
                      padding: '4px 12px',
                      borderRadius: 'var(--radius-xs)',
                      background: user.status === 'active' ? 'var(--success-light)' : 'var(--danger-light)',
                      color: user.status === 'active' ? 'var(--success)' : 'var(--danger)',
                      fontSize: 'var(--text-sm)',
                      fontWeight: 600,
                    }}>
                      {user.status === 'active' ? 'Hoạt động' : 'Chặn'}
                    </span>
                  </td>
                  <td style={{ padding: '16px' }}>
                    <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', flexWrap: 'wrap' }}>
                      {selectedUser?.id === user.id ? (
                        <>
                          <button
                            onClick={saveEdit}
                            style={{
                              background: 'var(--success-light)',
                              color: 'var(--success)',
                              border: 'none',
                              padding: '4px 8px',
                              borderRadius: 'var(--radius-xs)',
                              fontSize: 'var(--text-xs)',
                              cursor: 'pointer',
                            }}
                          >
                            Lưu
                          </button>
                          <button
                            onClick={() => setSelectedUser(null)}
                            style={{
                              background: 'var(--bg)',
                              color: 'var(--text-dim)',
                              border: '1px solid var(--border)',
                              padding: '4px 8px',
                              borderRadius: 'var(--radius-xs)',
                              fontSize: 'var(--text-xs)',
                              cursor: 'pointer',
                            }}
                          >
                            Huỷ
                          </button>
                        </>
                      ) : (
                        <>
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
                            onClick={() => editUser(user)}
                            style={{
                              background: 'var(--warning-light)',
                              color: 'var(--warning)',
                              border: 'none',
                              padding: '4px 8px',
                              borderRadius: 'var(--radius-xs)',
                              fontSize: 'var(--text-xs)',
                              cursor: 'pointer',
                            }}
                          >
                            Sửa credit
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
                        </>
                      )}
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