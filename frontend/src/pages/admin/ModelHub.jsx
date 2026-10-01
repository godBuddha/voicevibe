import { useState, useEffect, useCallback } from 'react';
import { useApi } from '../../hooks/useApi.jsx';
import ProvidersTab from './modelhub/ProvidersTab.jsx';
import ModelsTab from './modelhub/ModelsTab.jsx';
import StagesTab from './modelhub/StagesTab.jsx';
import FeaturesTab from './modelhub/FeaturesTab.jsx';
import PromptsTab from './modelhub/PromptsTab.jsx';
import PromptLibrary from '../prompts/PromptLibrary.jsx';

// AI Model Hub — Provider → Models → Capabilities → Compatibility.
// Shell 5 tab: Providers (card gọn + sync), Models (registry + filter +
// phân trang), Stages (gán model + selector lọc theo chức năng), Features
// (registry chức năng hệ thống), Prompts.
const TABS = [
  ['providers', 'Providers'],
  ['models', 'Mô hình'],
  ['stages', 'Công đoạn'],
  ['features', 'Chức năng'],
  ['library', 'Prompt của tôi'],
  ['prompts', 'Prompt hệ thống'],
];

export default function AdminModelHub({ embedded = false }) {
  const { api } = useApi();
  const [activeTab, setActiveTab] = useState('providers');
  const [providers, setProviders] = useState([]);
  const [stages, setStages] = useState([]);
  const [prompts, setPrompts] = useState([]);
  const [features, setFeatures] = useState([]);
  const [modelsFilter, setModelsFilter] = useState({}); // điều hướng "Xem models" giữa các tab
  const [toast, setToast] = useState(null);
  const [loading, setLoading] = useState(false);

  const notify = useCallback((msg, cls = 'ok') => {
    setToast({ msg, cls });
    clearTimeout(window._mhToast);
    window._mhToast = setTimeout(() => setToast(null), 5000);
  }, []);

  const loadCore = useCallback(async () => {
    try {
      const [providersData, stagesData, promptsData, featuresData] = await Promise.all([
        api.get('/v1/admin/providers'),
        api.get('/v1/admin/stages'),
        api.get('/v1/admin/prompts'),
        api.get('/v1/admin/features'),
      ]);
      setProviders(providersData.providers || []);
      // Backend: {stages: {stage: [rows]}, summary: {stage: str}} — order=0 là
      // chính, order>0 là chuỗi fallback (stage_chain đọc theo thứ tự này).
      const s = stagesData.stages || {};
      setStages(Object.keys(s).map((stage) => ({
        stage,
        summary: (stagesData.summary || {})[stage],
        models: (s[stage] || []).filter((x) => x.order === 0).map((x) => x.model || '(mặc định)'),
        fallback: (s[stage] || []).filter((x) => x.order > 0)
          .map((x) => `${x.model || '(mặc định)'}${x.provider_name ? ` @ ${x.provider_name}` : ''}`),
        items: s[stage] || [],
      })));
      setPrompts(promptsData.prompts || []);
      setFeatures(featuresData.features || []);
    } catch (err) {
      notify('Lỗi tải dữ liệu: ' + err.message, 'err');
    }
  }, [api, notify]);

  useEffect(() => { loadCore(); }, [loadCore]);

  const onViewModels = (providerId, compatibility) => {
    setModelsFilter({ provider_id: providerId || '', compatibility: compatibility || '', nonce: Date.now() });
    setActiveTab('models');
  };
  const onViewFeature = (featureKey) => {
    setModelsFilter({ feature: featureKey, nonce: Date.now() });
    setActiveTab('models');
  };

  return (
    <div style={{ padding: embedded ? '0' : '20px', maxWidth: '1400px', margin: '0 auto' }}>
      {!embedded && (
        <>
          <h1 style={{ fontSize: 'var(--text-4xl)', marginBottom: '10px', fontWeight: 700 }}>AI Model Hub</h1>
          <p style={{ color: 'var(--text-dim)', marginBottom: '16px', fontSize: 'var(--text-sm)' }}>
            Đồng bộ model từ providers → đánh dấu capability → đối chiếu chức năng hệ thống → gán vào công đoạn
          </p>
        </>
      )}

      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: '14px', gap: '2px' }}>
        {TABS.map(([key, label]) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            style={{
              padding: '7px 13px', border: 'none', background: 'transparent',
              color: activeTab === key ? 'var(--primary)' : 'var(--text-dim)',
              fontWeight: activeTab === key ? 600 : 400,
              borderBottom: activeTab === key ? '2px solid var(--primary)' : '2px solid transparent',
              cursor: 'pointer', fontSize: 'var(--text-sm)',
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'providers' && (
        <ProvidersTab providers={providers} api={api} notify={notify} reload={loadCore}
          onViewModels={onViewModels} loading={loading} setLoading={setLoading} />
      )}
      {activeTab === 'models' && (
        <ModelsTab api={api} notify={notify} initial={modelsFilter} loading={loading} setLoading={setLoading} />
      )}
      {activeTab === 'stages' && (
        <StagesTab stages={stages} providers={providers} api={api} notify={notify}
          reload={loadCore} loading={loading} setLoading={setLoading} />
      )}
      {activeTab === 'features' && (
        <FeaturesTab features={features} onViewModels={onViewFeature} />
      )}
      {activeTab === 'prompts' && (
        <PromptsTab prompts={prompts} api={api} notify={notify} reload={loadCore} />
      )}
      {activeTab === 'library' && (
        <PromptLibrary embedded />
      )}

      {toast && (
        <div style={{
          position: 'fixed', bottom: '20px', left: '50%', transform: 'translateX(-50%)',
          background: 'var(--surface)', border: `1px solid ${toast.cls === 'err' ? 'var(--danger)' : 'var(--success)'}`,
          color: toast.cls === 'err' ? 'var(--danger)' : 'var(--success)',
          padding: '8px 16px', borderRadius: 'var(--radius)', fontSize: 'var(--text-sm)',
          fontWeight: 600, zIndex: 'var(--z-toast)', maxWidth: '90vw', boxShadow: 'var(--shadow-md)',
        }}>
          {toast.msg}
        </div>
      )}
    </div>
  );
}
