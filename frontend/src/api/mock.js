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

const MOCK_PROVIDERS = [
  { id: 1, name: 'OpenAI', base_url: 'https://api.openai.com/v1', type: 'openai', status: 'active', models: ['gpt-4', 'gpt-4-turbo'] },
  { id: 2, name: 'DeepSeek', base_url: 'https://api.deepseek.com/v1', type: 'openai', status: 'active', models: ['deepseek-coder', 'deepseek-chat'] },
  { id: 3, name: 'Local Models', base_url: 'http://localhost:11434/v1', type: 'ollama', status: 'inactive', models: [] },
];

const MOCK_STAGES = [
  { stage: 'stt', models: ['whisper-large', 'whisper-base'], fallback: ['whisper-base'] },
  { stage: 'translate', models: ['gpt-4', 'gpt-4-turbo'], fallback: ['gpt-3.5-turbo'] },
  { stage: 'tts', models: ['natural-tts-hi'], fallback: ['microsoft-tts'] },
];

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

  if (path === '/v1/admin/providers' && method === 'GET') {
    return MOCK_PROVIDERS;
  }

  if (path.startsWith('/v1/admin/providers/') && path.endsWith('/test') && method === 'POST') {
    const id = parseInt(path.split('/')[3]);
    const provider = MOCK_PROVIDERS.find(p => p.id === id);
    return { success: true, status: 'ok', models: provider.models };
  }

  if (path.startsWith('/v1/admin/providers/') && path.endsWith('/pull') && method === 'POST') {
    return { success: true, models: ['gpt-4', 'gpt-4-turbo', 'davinci-002'] };
  }

  if (path === '/v1/admin/stages' && method === 'GET') {
    return MOCK_STAGES;
  }

  if (path.startsWith('/v1/admin/stages/') && method === 'PUT') {
    const stage = path.split('/').pop();
    return { success: true };
  }

  if (path === '/v1/admin/prompts' && method === 'GET') {
    return MOCK_PROMPTS;
  }

  if (path.startsWith('/v1/admin/prompts/') && method === 'PUT') {
    return { success: true };
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