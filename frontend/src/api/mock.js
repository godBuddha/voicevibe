const USER = {
  id: 1,
  name: 'Admin User',
  email: 'admin@voicevibe.local',
  avatar: '/avatar.png',
  role: 'admin',
};

// Mock usage: ĐẾM JOB theo loại (self-host miễn phí — không có đơn vị tiền).
const USAGE_BREAKDOWN = {
  tts: 12,
  translate: 8,
  dub: 3,
  stt: 5,
  subtitle: 2,
};

const VOICES = [
  { id: 1, name: 'Nữ miền Bắc (Hà Nội)', type: 'premade', gender: 'female', accent: 'north', demo: '/voice-north-female.mp3' },
  { id: 2, name: 'Nam miền Bắc (Hà Nội)', type: 'premade', gender: 'male', accent: 'north', demo: '/voice-north-male.mp3' },
  { id: 3, name: 'Nữ miền Trung (Huế)', type: 'premade', gender: 'female', accent: 'central', demo: '/voice-central-female.mp3' },
  { id: 4, name: 'Nam miền Trung (Đà Nẵng)', type: 'premade', gender: 'male', accent: 'central', demo: '/voice-central-male.mp3' },
  { id: 5, name: 'Nữ miền Nam (TP.HCM)', type: 'premade', gender: 'female', accent: 'south', demo: '/voice-south-female.mp3' },
  { id: 6, name: 'Nam miền Nam (TP.HCM)', type: 'premade', gender: 'male', accent: 'south', demo: '/voice-south-male.mp3' },
];

const MOCK_JOBS = [
  {
    id: 1,
    type: 'dub',
    status: 'completed',
    file: { name: 'conversation-en.mp4', size: 184_320_842, type: 'video/mp4', duration: 180 },
    fromLang: 'en',
    toLang: 'vi',
    voiceId: 1,
    createdAt: new Date(Date.now() - 4 * 60_000),
    completedAt: new Date(Date.now() - 1 * 60_000),
    result: { url: '/dubbed-result.mp4', transcript: 'Full transcript in Vietnamese...' },
  },
  {
    id: 2,
    type: 'tts',
    status: 'running',
    file: { name: 'script.txt', size: 248, type: 'text/plain', duration: null },
    text: 'Xin chào, đây là bài test giọng nói AI của hệ thống VoiceVibe...',
    voiceId: 1,
    createdAt: new Date(Date.now() - 45_000),
    startedAt: new Date(Date.now() - 30_000),
    progress: { percent: 67, step: 'TTS', message: 'Đang tạo file audio...' },
  },
  {
    id: 3,
    type: 'stt',
    status: 'queued',
    file: { name: 'audio-interview.mp3', size: 14_567_321, type: 'audio/mpeg', duration: 600 },
    createdAt: new Date(Date.now() - 60_000),
  },
];

const MOCK_V2USERS = [
  { id: 1, email: 'admin@voicevibe.local', role: 'admin', status: 'active' },
  { id: 2, email: 'user1@example.com', role: 'user', status: 'active' },
  { id: 3, email: 'user2@example.com', role: 'user', status: 'suspended' },
];

// Shape == BACKEND thật (_out_full): kind, enabled, api_key_set... (không có
// "type"/"status" mock cũ) — trang admin đọc shape backend trực tiếp, mock phải
// trả giống hệt để dev VITE_USE_MOCK=1 không vỡ.
const MOCK_PROVIDERS = [
  {
    id: 'mock-or', name: 'OpenRouter', kind: 'openai', base_url: 'https://openrouter.ai/api/v1',
    enabled: true, prefix_id: null, api_key_set: true, api_key_hint: '••••f41',
    created_at: 1767200000, models_count: 464, last_synced_at: 1767225600,
    breakdown: { compatible: 42, partial: 61, unknown: 348, incompatible: 13 },
  },
  {
    id: 'mock-ollama', name: 'Ollama local', kind: 'ollama', base_url: 'http://127.0.0.1:11434',
    enabled: true, prefix_id: null, api_key_set: false, api_key_hint: null,
    created_at: 1767200100, models_count: 3, last_synced_at: 1767225500,
    breakdown: { compatible: 2, partial: 0, unknown: 0, incompatible: 1 },
  },
];

const MOCK_MODELS = {
  items: [
    {
      id: 'mm1', provider_id: 'mock-or', provider_name: 'OpenRouter', provider_enabled: true,
      model_id: 'openai/gpt-4o', display_name: 'OpenAI: GPT-4o', org: 'openai',
      enabled: true, capability_source: 'official',
      capabilities: { text: true, chat: true, vision: true, functionCalling: true, structuredOutput: true, reasoning: true, streaming: true, translation: null },
      context_window: 128000, output_token_limit: 16384,
      pricing: { input: 0.0000025, output: 0.00001, currency: 'USD' },
      compatibility: { status: 'compatible', system_compatible: true, supported_features: ['text_generation', 'text_translation'], score: 47, reasons: [] },
      description: 'Chat đa năng, đa phương thức.', metadata: {}, last_synced_at: 1767225600,
    },
    {
      id: 'mm2', provider_id: 'mock-or', provider_name: 'OpenRouter', provider_enabled: true,
      model_id: 'mistralai/mistral-7b', display_name: 'Mistral: 7B', org: 'mistralai',
      enabled: true, capability_source: 'official',
      capabilities: { text: true, chat: true, vision: null, functionCalling: false, streaming: true },
      context_window: 32768, output_token_limit: null, pricing: null,
      compatibility: { status: 'partial', system_compatible: false, supported_features: [], partial_features: ['text_translation'], score: 24, reasons: ['text_translation: chưa xác nhận translation'] },
      description: '', metadata: {}, last_synced_at: 1767225600,
    },
    {
      id: 'mm3', provider_id: 'mock-ollama', provider_name: 'Ollama local', provider_enabled: true,
      model_id: 'qwen2.5:7b', display_name: 'qwen2.5:7b', org: null,
      enabled: false, capability_source: 'official',
      capabilities: { text: true, chat: true, tools: true, functionCalling: true },
      context_window: 32768, output_token_limit: null, pricing: null,
      compatibility: { status: 'compatible', system_compatible: true, supported_features: ['text_generation'], score: 29, reasons: [] },
      description: '', metadata: { parameter_size: '7.6B' }, last_synced_at: 1767225500,
    },
  ],
  total: 3, limit: 50, offset: 0,
  breakdown: { compatible: 2, partial: 1, unknown: 0, incompatible: 0 },
  providers: { 'mock-or': 'OpenRouter', 'mock-ollama': 'Ollama local' },
};

const MOCK_FEATURES = {
  features: [
    { key: 'text_generation', label: 'Sinh văn bản / Chat', stage: null, required: ['text', 'chat'], optional: [], local_engine: false, models_compatible: 2, models_partial: 0 },
    { key: 'text_translation', label: 'Dịch văn bản', stage: 'translate', required: ['text', 'chat'], optional: ['translation'], local_engine: false, models_compatible: 1, models_partial: 1 },
    { key: 'speech_to_text', label: 'Giọng nói → văn bản', stage: 'stt', required: ['speechToText'], optional: [], local_engine: false, models_compatible: 0, models_partial: 0 },
    { key: 'text_to_speech', label: 'Văn bản → giọng nói', stage: 'tts', required: ['textToSpeech'], optional: [], local_engine: false, models_compatible: 0, models_partial: 0 },
    { key: 'voice_cloning', label: 'Nhân bản giọng nói', stage: null, required: [], optional: [], local_engine: true, models_compatible: 0, models_partial: 0 },
  ],
};

// Shape == BACKEND GET /v1/admin/stages: {stages: {stage: [rows]}, summary}
const MOCK_STAGES = {
  stages: {
    stt: [], translate: [
      { id: 1, provider_id: 'mock-or', model: 'openai/gpt-4o', params: {}, order: 0, provider_name: 'OpenRouter' },
    ],
    retranslate: [], tts: [], dub: [],
  },
  summary: { translate: 'openai/gpt-4o qua OpenRouter', stt: 'engine local mặc định' },
};

const MOCK_PROMPTS = [
  { task_key: 'translate', template: 'Dịch chính xác đoạn sau sang {target_lang}: {text}' },
  { task_key: 'transcript', template: 'Chuyển ngữ đoạn audio sau thành văn bản tiếng {lang}:' },
];

const MOCK_SETTINGS = {
  app_name: 'VoiceVibe',
  app_url: 'https://voicevibe.local',
  default_language: 'vi',
  max_file_size: '200',
  max_duration: '600',
  auth_session_ttl: '86400',
  auth_refresh_ttl: '604800',
  rate_limit_rpm: '60',
  rate_limit_burst: '100',
  storage_provider: 'local',
  storage_endpoint: '/media',
  demucs_enabled: 'true',
  demucs_model: 'htdemucs',
};

export async function mockRequest(method, path, options) {
  const { body, query } = options;
  await new Promise(r => setTimeout(r, Math.random() * 300 + 50));

  if (path === '/v1/auth/me' && method === 'GET') {
    return { ok: true, data: USER };
  }

  if (path === '/v1/me' && method === 'GET') {
    return USER;
  }

  if (path === '/v1/usage' && method === 'GET') {
    return {
      total_jobs: Object.values(USAGE_BREAKDOWN).reduce((a, b) => a + b, 0),
      by_type: USAGE_BREAKDOWN,
      by_status: { done: 20, running: 1, queued: 2, failed: 2, cancelled: 5 },
      running: 1,
    };
  }

  if (path === '/v1/jobs' && method === 'GET') {
    const limit = query?.limit || 50;
    return { items: MOCK_JOBS.slice(0, limit), total: MOCK_JOBS.length };
  }

  if (path.startsWith('/v1/jobs/') && method === 'GET') {
    const id = parseInt(path.split('/').pop());
    const job = MOCK_JOBS.find(j => j.id === id);
    if (!job) throw new Error('Job not found');
    return job;
  }

  if (path === '/v1/jobs' && method === 'POST') {
    const newJob = {
      id: MOCK_JOBS.length + 1,
      type: body.type,
      status: 'queued',
      createdAt: new Date(),
      ...body,
    };
    MOCK_JOBS.unshift(newJob);
    return { id: newJob.id, status: 'queued' };
  }

  if (path === '/v1/voices' && method === 'GET') {
    return VOICES;
  }

  if (path === '/v1/keys' && method === 'GET') {
    return [
      { id: 1, key: 'vv_sk_live_abc123xyz789', name: 'Production API Key', permissions: 'full', created: new Date('2024-01-20'), lastUsed: new Date('2024-09-28') },
      { id: 2, key: 'vv_sk_test_def456uvw012', name: 'Test API Key', permissions: 'limited', created: new Date('2024-03-15'), lastUsed: null },
    ];
  }

  if (path === '/v1/keys' && method === 'POST') {
    const key = 'vv_sk_' + Math.random().toString(36).substring(2, 14);
    return { key, id: Date.now(), name: body.name, permissions: body.permissions };
  }

  if (path.startsWith('/v1/keys/') && method === 'DELETE') {
    return { success: true };
  }

  if (path === '/v1/admin/users' && method === 'GET') {
    return MOCK_V2USERS;
  }

  // Shape admin == BACKEND thật (trang admin đọc shape backend trực tiếp, mock
  // phải trả giống hệt để VITE_USE_MOCK=1 không vỡ — xem pages/admin/modelhub).
  if (path === '/v1/admin/providers' && method === 'GET') {
    return { providers: MOCK_PROVIDERS };
  }

  if (path === '/v1/admin/providers' && method === 'POST') {
    return { ...MOCK_PROVIDERS[0], id: 'mock-new', name: body.name, base_url: body.base_url,
             kind: body.kind || 'openai', models_count: 0, last_synced_at: null,
             breakdown: { compatible: 0, partial: 0, unknown: 0, incompatible: 0 } };
  }

  if (path.startsWith('/v1/admin/providers/') && path.endsWith('/test') && method === 'POST') {
    return { id: 'mock-or', ok: true, detail: '3 model khả dụng' };
  }

  if (path.startsWith('/v1/admin/providers/') && path.endsWith('/sync') && method === 'POST') {
    return { provider_id: 'mock-or', kind: 'openai', synced: 464, added: 0, updated: 464,
             removed: 0, duration_ms: 1200, errors: [] };
  }

  if (path.startsWith('/v1/admin/providers/') && path.endsWith('/models') && method === 'GET') {
    return { provider_id: 'mock-or', kind: 'openai', models: [{ name: 'gpt-4' }, { name: 'qwen2.5' }] };
  }

  if (path === '/v1/admin/models' && method === 'GET') {
    return MOCK_MODELS;
  }

  if (path.startsWith('/v1/admin/models/') && method === 'PATCH') {
    return { ...MOCK_MODELS.items[0], enabled: !!body.enabled };
  }

  if (path === '/v1/admin/features' && method === 'GET') {
    return MOCK_FEATURES;
  }

  if (path === '/v1/admin/stages' && method === 'GET') {
    return MOCK_STAGES;
  }

  if (path.startsWith('/v1/admin/stages/') && method === 'PUT') {
    const stage = path.split('/').pop();
    return { stage, provider_id: body.provider_id || null, model: body.model || '',
             order: body.order || 0 };
  }

  if (path === '/v1/admin/prompts' && method === 'GET') {
    return { prompts: MOCK_PROMPTS };
  }

  if (path.startsWith('/v1/admin/prompts/') && method === 'PUT') {
    return { task_key: path.split('/').pop(), content: body.content || '' };
  }

  if (path.startsWith('/v1/admin/prompts/') && path.endsWith('/reset') && method === 'POST') {
    return { task_key: path.split('/').pop(), is_default: true };
  }

  if (path.startsWith('/v1/admin/users/') && path.includes('/reset-password') && method === 'POST') {
    return { success: true, tempPassword: 'Temp123!' };
  }

  if (path.startsWith('/v1/admin/users/') && path.includes('/activate') && method === 'POST') {
    return { success: true };
  }

  if (path.startsWith('/v1/admin/users/') && path.includes('/deactivate') && method === 'POST') {
    return { success: true };
  }

  if (path === '/v1/admin/users' && method === 'POST') {
    return { id: 999, email: body.email, role: body.role, status: 'active' };
  }

  if (path === '/v1/admin/settings' && method === 'GET') {
    return MOCK_SETTINGS;
  }

  throw new Error('Unknown mock endpoint');
}