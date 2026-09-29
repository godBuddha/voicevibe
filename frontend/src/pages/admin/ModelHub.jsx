import { useState, useEffect } from 'react';
import { useApi } from '../../hooks/useApi.jsx';

export default function AdminModelHub() {
  const { api } = useApi();
  const [activeTab, setActiveTab] = useState('providers');
  const [providers, setProviders] = useState([]);
  const [stages, setStages] = useState([]);
  const [prompts, setPrompts] = useState([]);
  const [selectedProvider, setSelectedProvider] = useState(null);
  const [editingPrompt, setEditingPrompt] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadData();
  }, [api]);

  const loadData = async () => {
    try {
      const providersData = await api.get('/v1/admin/providers');
      const stagesData = await api.get('/v1/admin/stages');
      const promptsData = await api.get('/v1/admin/prompts');
      setProviders(providersData);
      setStages(stagesData);
      setPrompts(promptsData);
    } catch {}
  };

  const addProvider = async () => {
    const name = prompt('Tên provider:');
    if (!name) return;
    const type = prompt('Loại (openai/ollama):') || 'openai';
    try {
      const newProvider = { id: Date.now(), name, base_url: '', type, status: 'inactive', models: [] };
      setProviders([...providers, newProvider]);
      setSelectedProvider(newProvider);
    } catch {}
  };

  const deleteProvider = async (id) => {
    if (!confirm('Xoá provider?')) return;
    try {
      await api.del(`/v1/admin/providers/${id}`);
      setProviders(providers.filter(p => p.id !== id));
      if (selectedProvider?.id === id) setSelectedProvider(null);
    } catch {}
  };

  const saveProvider = async () => {
    if (!selectedProvider) return;
    setLoading(true);
    try {
      await api.put(`/v1/admin/providers/${selectedProvider.id}`, { body: selectedProvider });
      setProviders(providers.map(p => p.id === selectedProvider.id ? selectedProvider : p));
      setSelectedProvider(null);
    } catch (err) {
      alert('Lỗi khi lưu provider: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const testProvider = async (id) => {
    setLoading(true);
    try {
      const res = await api.post(`/v1/admin/providers/${id}/test`);
      alert(res.models?.length ? `Đã kết nối, có ${res.models.length} models` : 'Kết nối thành công nhưng không có model');
    } catch (err) {
      alert('Lỗi kết nối: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const pullModels = async (id) => {
    setLoading(true);
    try {
      const res = await api.post(`/v1/admin/providers/${id}/pull`);
      setProviders(providers.map(p => p.id === id ? { ...p, models: res.models || [] } : p));
    } catch (err) {
      alert('Lỗi khi pull models: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const updateStage = async (stage, models, fallback) => {
    try {
      await api.put(`/v1/admin/stages/${stage}`, { body: { models, fallback } });
      setStages(stages.map(s => s.stage === stage ? { ...s, models, fallback } : s));
    } catch (err) {
      alert('Lỗi khi save stage: ' + err.message);
    }
  };

  const editPrompt = (prompt) => {
    setEditingPrompt({ ...prompt });
  };

  const savePrompt = async () => {
    try {
      await api.put(`/v1/admin/prompts/${editingPrompt.task_key}`, { body: editingPrompt });
      setPrompts(prompts.map(p => p.task_key === editingPrompt.task_key ? editingPrompt : p));
      setEditingPrompt(null);
    } catch (err) {
      alert('Lỗi khi save prompt: ' + err.message);
    }
  };

  const resetPrompt = async (taskKey) => {
    if (!confirm('Reset về prompt mặc định?')) return;
    try {
      const defaultPrompts = {
        translate: 'Dịch chính xác đoạn sau sang {target_lang}: {text}',
        transcript: 'Chuyển ngữ đoạn audio sau thành văn bản tiếng {lang}:',
      };
      const resetTo = defaultPrompts[taskKey];
      await api.put(`/v1/admin/prompts/${taskKey}`, { body: { template: resetTo } });
      setPrompts(prompts.map(p => p.task_key === taskKey ? { ...p, template: resetTo } : p));
    } catch (err) {
      alert('Lỗi khi reset prompt: ' + err.message);
    }
  };

  return (
    <div style={{ padding: '40px', maxWidth: '1400px', margin: '0 auto' }}>
      <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '24px', fontWeight: 700 }}>
        AI Model Hub
      </h1>
      <p style={{ color: 'var(--text-dim)', marginBottom: '48px' }}>
        Quản lý providers, mô hình và pipeline AI
      </p>

      {/* Tabs */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: '32px' }}>
        {['providers', 'stages', 'prompts'].map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '12px 24px',
              border: 'none',
              background: activeTab === tab ? 'var(--bg)' : 'transparent',
              color: activeTab === tab ? 'var(--text)' : 'var(--text-dim)',
              fontWeight: activeTab === tab ? 600 : 400,
              borderBottom: activeTab === tab ? '2px solid var(--primary)' : 'none',
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {tab === 'providers' ? 'Providers' : tab === 'stages' ? 'Stages' : 'Prompts'}
          </button>
        ))}
      </div>

      {/* Providers */}
      {activeTab === 'providers' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
            <h3 style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>AI Providers</h3>
            <button
              onClick={addProvider}
              style={{
                background: 'var(--gradient)',
                color: '#fff',
                border: 'none',
                padding: '8px 16px',
                borderRadius: 'var(--radius)',
                fontSize: 'var(--text-sm)',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              + Thêm Provider
            </button>
          </div>
          
          {selectedProvider && (
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '24px', marginBottom: '24px' }}>
              <h4 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, marginBottom: '16px' }}>
                Chỉnh sửa provider: {selectedProvider.name}
              </h4>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '20px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '8px' }}>
                    Base URL
                  </label>
                  <input
                    type="text"
                    value={selectedProvider.base_url}
                    onChange={(e) => setSelectedProvider({ ...selectedProvider, base_url: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: 'var(--radius)',
                      border: '1px solid var(--border)',
                      fontSize: 'var(--text-sm)',
                      background: 'var(--bg)',
                      color: 'var(--text)',
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '8px' }}>
                    API Key
                  </label>
                  <input
                    type="password"
                    value={selectedProvider.api_key || ''}
                    onChange={(e) => setSelectedProvider({ ...selectedProvider, api_key: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: 'var(--radius)',
                      border: '1px solid var(--border)',
                      fontSize: 'var(--text-sm)',
                      background: 'var(--bg)',
                      color: 'var(--text)',
                    }}
                  />
                </div>
              </div>
              <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                <button
                  onClick={() => setSelectedProvider(null)}
                  style={{
                    background: 'var(--bg)',
                    color: 'var(--text-dim)',
                    border: '1px solid var(--border)',
                    padding: '8px 16px',
                    borderRadius: 'var(--radius)',
                    fontWeight: 600,
                    fontSize: 'var(--text-sm)',
                    cursor: 'pointer',
                  }}
                >
                  Huỷ
                </button>
                <button
                  onClick={saveProvider}
                  disabled={loading}
                  style={{
                    background: 'var(--gradient)',
                    color: '#fff',
                    border: 'none',
                    padding: '8px 16px',
                    borderRadius: 'var(--radius)',
                    fontWeight: 600,
                    fontSize: 'var(--text-sm)',
                    cursor: loading ? 'not-allowed' : 'pointer',
                    opacity: loading ? 0.6 : 1,
                  }}
                >
                  Lưu
                </button>
              </div>
            </div>
          )}

          <div style={{ display: 'grid', gap: '16px' }}>
            {providers.map(provider => (
              <div
                key={provider.id}
                style={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-lg)',
                  padding: '20px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: 'var(--text-lg)', marginBottom: '8px' }}>{provider.name}</div>
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '4px' }}>
                    Type: <span style={{ fontWeight: 600 }}>{provider.type}</span>
                  </div>
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '8px' }}>
                    URL: <span style={{ fontFamily: 'monospace', background: 'var(--bg)', padding: '2px 6px', borderRadius: '2px' }}>{provider.base_url || 'N/A'}</span>
                  </div>
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                    Models: {provider.models?.join(', ') || 'Chưa có'}
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                    <button
                      onClick={() => testProvider(provider.id)}
                      disabled={loading}
                      style={{
                        background: 'var(--info-light)',
                        color: 'var(--info)',
                        border: 'none',
                        padding: '6px 12px',
                        borderRadius: 'var(--radius)',
                        fontWeight: 600,
                        fontSize: 'var(--text-xs)',
                        cursor: 'pointer',
                      }}
                    >
                      Test kết nối
                    </button>
                    <button
                      onClick={() => pullModels(provider.id)}
                      disabled={loading}
                      style={{
                        background: 'var(--warning-light)',
                        color: 'var(--warning)',
                        border: 'none',
                        padding: '6px 12px',
                        borderRadius: 'var(--radius)',
                        fontWeight: 600,
                        fontSize: 'var(--text-xs)',
                        cursor: 'pointer',
                      }}
                    >
                      Pull models
                    </button>
                    <button
                      onClick={() => setSelectedProvider(provider)}
                      style={{
                        background: 'var(--primary-light)',
                        color: 'var(--primary)',
                        border: 'none',
                        padding: '6px 12px',
                        borderRadius: 'var(--radius)',
                        fontWeight: 600,
                        fontSize: 'var(--text-xs)',
                        cursor: 'pointer',
                      }}
                    >
                      Sửa
                    </button>
                    <button
                      onClick={() => deleteProvider(provider.id)}
                      style={{
                        background: 'var(--danger-light)',
                        color: 'var(--danger)',
                        border: 'none',
                        padding: '6px 12px',
                        borderRadius: 'var(--radius)',
                        fontWeight: 600,
                        fontSize: 'var(--text-xs)',
                        cursor: 'pointer',
                      }}
                    >
                      Xoá
                    </button>
                  </div>
                  <div style={{ fontSize: 'var(--text-xs)', color: provider.status === 'active' ? 'var(--success)' : 'var(--danger)', textAlign: 'right' }}>
                    {provider.status === 'active' ? '🟢 Connected' : '🔴 Inactive'}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Stages */}
      {activeTab === 'stages' && (
        <div>
          <h3 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, marginBottom: '24px' }}>Các công đoạn xử lý</h3>
          <div style={{ display: 'grid', gap: '24px' }}>
            {stages.map(sg => (
              <div
                key={sg.stage}
                style={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-lg)',
                  padding: '24px',
                }}
              >
                <h4 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, marginBottom: '20px', textTransform: 'capitalize' }}>
                  {sg.stage}
                </h4>
                <div style={{ marginBottom: '20px' }}>
                  <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '8px', fontWeight: 600 }}>
                    Mô hình chính ({sg.models.length})
                  </label>
                  <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                    {sg.models.map((m, i) => (
                      <li key={i} style={{
                        padding: '6px 12px',
                        background: 'var(--primary-light)',
                        color: 'var(--primary)',
                        borderRadius: 'var(--radius)',
                        fontSize: 'var(--text-sm)',
                        fontWeight: 600,
                      }}>
                        {m}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginBottom: '8px', fontWeight: 600 }}>
                    Fallback chain ({sg.fallback?.length || 0})
                  </label>
                  <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                    {(sg.fallback || []).map((m, i) => (
                      <li key={i} style={{
                        padding: '6px 12px',
                        background: 'var(--warning-light)',
                        color: 'var(--warning)',
                        borderRadius: 'var(--radius)',
                        fontSize: 'var(--text-sm)',
                        fontWeight: 600,
                      }}>
                        {m}
                      </li>
                    ))}
                  </ul>
                </div>
                <div style={{ marginTop: '20px', fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                  <button
                    style={{
                      background: 'var(--primary-light)',
                      color: 'var(--primary)',
                      border: 'none',
                      padding: '6px 12px',
                      borderRadius: 'var(--radius)',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Chỉnh sửa
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Prompts */}
      {activeTab === 'prompts' && (
        <div>
          <h3 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, marginBottom: '24px' }}>Prompt Templates</h3>
          <div style={{ display: 'grid', gap: '24px' }}>
            {prompts.map(p => (
              <div
                key={p.task_key}
                style={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-lg)',
                  padding: '24px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <h4 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, textTransform: 'capitalize' }}>
                    {p.task_key}
                  </h4>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      onClick={() => resetPrompt(p.task_key)}
                      style={{
                        background: 'var(--warning-light)',
                        color: 'var(--warning)',
                        border: 'none',
                        padding: '6px 12px',
                        borderRadius: 'var(--radius)',
                        fontWeight: 600,
                        fontSize: 'var(--text-xs)',
                        cursor: 'pointer',
                      }}
                    >
                      Reset mặc định
                    </button>
                    <button
                      onClick={() => editPrompt(p)}
                      style={{
                        background: 'var(--primary-light)',
                        color: 'var(--primary)',
                        border: 'none',
                        padding: '6px 12px',
                        borderRadius: 'var(--radius)',
                        fontWeight: 600,
                        fontSize: 'var(--text-xs)',
                        cursor: 'pointer',
                      }}
                    >
                      Sửa
                    </button>
                  </div>
                </div>
                {editingPrompt?.task_key === p.task_key ? (
                  <div>
                    <textarea
                      value={editingPrompt.template}
                      onChange={(e) => setEditingPrompt({ ...editingPrompt, template: e.target.value })}
                      rows={4}
                      style={{
                        width: '100%',
                        padding: '12px',
                        borderRadius: 'var(--radius)',
                        border: '1px solid var(--border)',
                        fontSize: 'var(--text-base)',
                        fontFamily: 'monospace',
                        background: 'var(--bg)',
                        color: 'var(--text)',
                        resize: 'vertical',
                      }}
                    />
                    <div style={{ display: 'flex', gap: '12px', marginTop: '16px', justifyContent: 'flex-end' }}>
                      <button
                        onClick={() => setEditingPrompt(null)}
                        style={{
                          background: 'var(--bg)',
                          color: 'var(--text-dim)',
                          border: '1px solid var(--border)',
                          padding: '8px 16px',
                          borderRadius: 'var(--radius)',
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        Huỷ
                      </button>
                      <button
                        onClick={savePrompt}
                        style={{
                          background: 'var(--gradient)',
                          color: '#fff',
                          border: 'none',
                          padding: '8px 16px',
                          borderRadius: 'var(--radius)',
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        Lưu
                      </button>
                    </div>
                  </div>
                ) : (
                  <pre style={{
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius)',
                    padding: '16px',
                    fontSize: 'var(--text-sm)',
                    color: 'var(--text)',
                    lineHeight: 1.6,
                    overflowX: 'auto',
                  }}>
                    {p.template}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}