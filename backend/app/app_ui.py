"""User-facing dashboard UI — bố cục sidebar + topbar theo mẫu SaaS voice.

Single page, vanilla JS, hash routing (#/dashboard, #/dub, #/tts, #/voices,
#/stt, #/jobs, #/api). Không build step — self-host chỉ cần Python.
Usage donut đọc số liệu THẬT từ GET /v1/usage (aggregate credit_ledger).
"""

APP_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YupVox-Clone — AI Voice cho một thế giới mới</title>
<style>
  :root { --bg:#f6f5fb; --card:#ffffff; --line:#e8e6f5; --fg:#23213a; --mut:#8b88a8;
          --acc:#7c5cff; --acc2:#a78bfa; --ok:#22c58b; --warn:#ffb020; --err:#ff5d73;
          --side:#ffffff; }
  * { box-sizing:border-box; }
  body { background:var(--bg); color:var(--fg); font:14.5px/1.55 system-ui,-apple-system,sans-serif; margin:0; }
  a { color:var(--acc); text-decoration:none; }
  h1,h2,h3 { margin:0 0 8px; }
  .mut { color:var(--mut); font-size:12.5px; }

  /* ---- layout ---- */
  #shell { display:flex; min-height:100vh; }
  #sidebar { width:248px; background:var(--side); border-right:1px solid var(--line);
             padding:18px 14px; display:flex; flex-direction:column; gap:4px;
             position:fixed; top:0; bottom:0; left:0; overflow-y:auto; z-index:30; }
  main { margin-left:248px; flex:1; padding:0 26px 40px; }
  @media (max-width: 920px) {
    #sidebar { display:none; }
    main { margin-left:0; }
    #burger { display:inline-flex !important; }
  }
  #burger { display:none; background:var(--card); border:1px solid var(--line);
            border-radius:10px; padding:8px 12px; cursor:pointer; }

  /* ---- sidebar ---- */
  .logo { display:flex; gap:10px; align-items:center; padding:6px 8px 16px; }
  .logo .mark { width:38px; height:38px; border-radius:12px; background:linear-gradient(135deg,var(--acc),var(--acc2));
                display:flex; align-items:center; justify-content:center; font-size:19px; }
  .logo b { font-size:16px; } .logo .mut { line-height:1.2; }
  .nav { display:flex; flex-direction:column; gap:2px; }
  .nav .group { color:var(--mut); font-size:11px; text-transform:uppercase; letter-spacing:.08em;
                padding:14px 10px 6px; }
  .nav a { display:flex; gap:10px; align-items:center; padding:9px 12px; border-radius:10px;
           color:var(--fg); cursor:pointer; font-size:14px; }
  .nav a:hover { background:#f3f1fc; }
  .nav a.on { background:linear-gradient(90deg,var(--acc),var(--acc2)); color:#fff; font-weight:600; }
  .nav a.soon { color:var(--mut); opacity:.65; }
  .nav a.soon:hover { background:#f3f1fc; }
  .sidecard { margin-top:auto; background:linear-gradient(160deg,#f4f0ff,#eef9f4);
              border:1px solid var(--line); border-radius:14px; padding:14px; font-size:13px; }
  .sidecard b { font-size:16px; }
  .sidecard button { width:100%; margin-top:8px; }

  /* ---- topbar ---- */
  .topbar { display:flex; gap:14px; align-items:center; padding:16px 0 18px; flex-wrap:wrap; }
  .search { flex:1; min-width:220px; max-width:430px; background:var(--card); border:1px solid var(--line);
            border-radius:12px; padding:10px 14px; display:flex; gap:8px; align-items:center; }
  .search input { border:none; outline:none; background:transparent; width:100%; font:inherit; color:var(--fg); }
  .credits-pill { background:var(--card); border:1px solid var(--line); border-radius:99px;
                  padding:9px 16px; font-size:13.5px; }
  .who { display:flex; gap:9px; align-items:center; }
  .avatar { width:36px; height:36px; border-radius:50%; background:linear-gradient(135deg,var(--acc),var(--acc2));
            color:#fff; display:flex; align-items:center; justify-content:center; font-weight:700; }

  /* ---- cards / pages ---- */
  .page { display:none; } .page.on { display:block; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:16px; padding:20px; }
  .grid2 { display:grid; grid-template-columns: 1.6fr 1fr; gap:16px; margin-top:16px; }
  @media (max-width: 980px) { .grid2 { grid-template-columns:1fr; } }
  .hero { background:linear-gradient(120deg,#7c5cff 0%,#a78bfa 55%,#22c58b 130%);
          color:#fff; border-radius:20px; padding:30px; }
  .hero h1 { font-size:26px; } .hero p { opacity:.92; max-width:520px; }
  .hero button { background:#fff; color:var(--acc); border:none; border-radius:12px;
                 padding:11px 22px; font-weight:700; cursor:pointer; margin-top:14px; font-size:15px; }
  .statrow { display:flex; gap:22px; flex-wrap:wrap; margin-top:18px; }
  .stat b { font-size:17px; display:block; } .stat span { opacity:.85; font-size:12.5px; }
  .chips { display:flex; gap:10px; flex-wrap:wrap; margin-top:10px; }
  .chip { background:#f6f4ff; border:1px solid var(--line); border-radius:10px; padding:9px 14px;
          cursor:pointer; font-size:13.5px; }
  .chip:hover { border-color:var(--acc); }
  label { display:block; color:var(--mut); font-size:12.5px; margin:12px 0 5px; }
  input, select, textarea { background:#fbfaff; border:1px solid var(--line); color:var(--fg);
          border-radius:10px; padding:10px 12px; width:100%; font:inherit; }
  textarea { min-height:96px; resize:vertical; }
  button.go { background:linear-gradient(90deg,var(--acc),var(--acc2)); border:none; color:#fff;
              border-radius:11px; padding:11px 22px; font-weight:700; cursor:pointer; margin-top:16px; font-size:15px; }
  button.ghost { background:transparent; border:1px solid var(--line); color:var(--mut);
                 border-radius:9px; padding:7px 13px; cursor:pointer; font-size:13px; }
  .row { display:flex; gap:12px; flex-wrap:wrap; } .row > div { flex:1; min-width:170px; }
  .status { margin-top:10px; font-size:13.5px; } .ok { color:var(--ok); } .err { color:var(--err); }
  .job { border:1px solid var(--line); border-radius:12px; padding:13px 15px; margin-bottom:10px; background:#fff; }
  .job .h { display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap; align-items:center; }
  .pill { font-size:12px; padding:3px 11px; border-radius:99px; }
  .pill.done { background:#e6f9f1; color:var(--ok); } .pill.running { background:#fff5e0; color:#c77c00; }
  .pill.failed { background:#ffe9ec; color:var(--err); } .pill.queued { background:#f0eefb; color:var(--mut); }
  audio, video { width:100%; margin-top:10px; border-radius:10px; }
  .donut-wrap { display:flex; gap:18px; align-items:center; }
  .legend { font-size:13px; } .legend i { display:inline-block; width:10px; height:10px;
           border-radius:3px; margin-right:7px; }
  .usagebar { height:8px; border-radius:99px; background:#f0eefb; margin:7px 0; overflow:hidden; }
  .usagebar i { display:block; height:100%; border-radius:99px; }
  table.keys { width:100%; border-collapse:collapse; font-size:13.5px; }
  table.keys td, table.keys th { text-align:left; padding:8px 6px; border-bottom:1px solid var(--line); }
  code { background:#f3f1fc; border-radius:6px; padding:2px 7px; font-size:12.5px; }
  pre { background:#23213a; color:#d7d5f5; border-radius:12px; padding:14px; overflow-x:auto; font-size:12.5px; }
  #gate { max-width:420px; margin:90px auto; text-align:center; }
  .soonbox { text-align:center; padding:40px 20px; }
</style>
</head>
<body>

<div id="gate" class="card" style="max-width:420px;margin:90px auto;text-align:center">
  <h1>🎙️ YupVox-Clone</h1>
  <p class="mut">AI Voice cho một thế giới mới — nhập API key để bắt đầu</p>
  <input id="gatekey" type="password" placeholder="X-API-Key (yv_... hoặc dev key)"
         style="margin:14px 0" onkeydown="if(event.key==='Enter')enter()">
  <button class="go" style="width:100%" onclick="enter()">Vào bảng điều khiển</button>
  <p id="gmsg" class="err"></p>
</div>

<div id="shell" style="display:none">
  <aside id="sidebar">
    <div class="logo"><div class="mark">🎙️</div>
      <div><b>YupVox-Clone</b><div class="mut">AI Voice cho một thế giới mới</div></div></div>
    <nav class="nav">
      <a data-page="dashboard" class="on" onclick="go('dashboard')">🏠 Bảng điều khiển</a>
      <div class="group">Tạo nội dung với AI</div>
      <a data-page="tts" onclick="go('tts')">🗣️ Chuyển văn bản thành giọng nói</a>
      <a data-page="tts" onclick="go('tts')">🎚️ TTS Studio</a>
      <a class="soon" onclick="soon('Dịch phụ đề thành giọng nói')">💬 Chuyển phụ đề thành giọng nói</a>
      <a data-page="voices" onclick="go('voices')">🎭 Tạo giọng nói của riêng bạn</a>
      <div class="group">Dịch thuật</div>
      <a class="soon" onclick="soon('Dịch văn bản')">🌐 Dịch văn bản</a>
      <a class="soon" onclick="soon('Dịch phụ đề')">📄 Dịch phụ đề</a>
      <a data-page="dub" onclick="go('dub')">🔊 Dịch âm thanh</a>
      <a data-page="dub" onclick="go('dub')">🎬 Dịch video</a>
      <div class="group">AI Giọng nói &amp; Video</div>
      <a data-page="stt" onclick="go('stt')">📝 Chuyển giọng nói thành văn bản</a>
      <a class="soon" onclick="soon('Tạo video bằng AI')">🎥 Tạo video bằng AI</a>
      <a class="soon" onclick="soon('Thay đổi giọng nói')">🎚️ Thay đổi giọng nói</a>
      <div class="group">Khác</div>
      <a data-page="api" onclick="go('api')">🔌 API cho nhà phát triển</a>
    </nav>
    <div class="sidecard">
      🎁 Miễn phí <b id="side-free">50.000</b> Credits
      <div class="mut">Khám phá các tính năng AI giọng nói</div>
      <button class="go" onclick="go('dub')">Bắt đầu ngay</button>
    </div>
  </aside>

  <main>
    <div class="topbar">
      <button id="burger" onclick="toggleSide()">☰</button>
      <div class="search">🔍<input id="q" placeholder="Tìm kiếm dự án, giọng nói, công cụ…"></div>
      <div class="credits-pill">💰 <b id="top-credits">…</b> Credits</div>
      <div class="who"><div class="avatar">C</div><div><b>Xin chào, Creator!</b><div class="mut" id="whokey"></div></div></div>
    </div>

    <!-- DASHBOARD -->
    <section id="page-dashboard" class="page on">
      <div class="hero">
        <h1>Dịch Audio, Video Online</h1>
        <p>Xóa nhòa cách biệt ngôn ngữ — dịch nhanh với AI, giữ nguyên giọng nhân vật,
           chạy trên hạ tầng của chính bạn.</p>
        <button onclick="go('dub')">Bắt đầu ngay →</button>
        <div class="statrow">
          <div class="stat"><b id="st-voices">25+</b><span>Giọng đọc AI</span></div>
          <div class="stat"><b>2+</b><span>Ngôn ngữ local</span></div>
          <div class="stat"><b>3–8s</b><span>Clone giọng</span></div>
          <div class="stat"><b id="st-free">50.000</b><span>Credits miễn phí</span></div>
        </div>
      </div>
      <div class="grid2">
        <div class="card">
          <h3>Công cụ nhanh</h3>
          <div class="chips">
            <span class="chip" onclick="go('tts')">🗣️ Văn bản → giọng nói</span>
            <span class="chip" onclick="go('dub')">🎬 Dịch &amp; lồng tiếng</span>
            <span class="chip" onclick="go('voices')">🎭 Tạo giọng clone</span>
            <span class="chip" onclick="go('stt')">📝 Giọng nói → văn bản</span>
            <span class="chip" onclick="go('api')">🔑 Quản lý API key</span>
          </div>
          <h3 style="margin-top:20px">Dự án gần đây</h3>
          <div id="dash-jobs" class="mut">…</div>
          <a href="#/jobs" onclick="go('jobs')">Xem tất cả →</a>
        </div>
        <div class="card">
          <h3>Mức sử dụng của bạn</h3>
          <div class="donut-wrap">
            <svg width="120" height="120" viewBox="0 0 120 120">
              <circle cx="60" cy="60" r="48" fill="none" stroke="#f0eefb" stroke-width="14"/>
              <circle id="donut" cx="60" cy="60" r="48" fill="none" stroke="var(--acc)"
                      stroke-width="14" stroke-linecap="round"
                      stroke-dasharray="0 302" transform="rotate(-90 60 60)"/>
              <text x="60" y="56" text-anchor="middle" font-size="17" font-weight="700"
                    fill="#23213a" id="donut-used">0</text>
              <text x="60" y="74" text-anchor="middle" font-size="10" fill="#8b88a8" id="donut-total">/ 50.000</text>
            </svg>
            <div class="legend" id="legend">…</div>
          </div>
          <div class="mut" style="margin-top:12px">Số liệu thật từ credit ledger — cập nhật theo từng job.</div>
        </div>
      </div>
    </section>

    <!-- DUB -->
    <section id="page-dub" class="page">
      <div class="card">
        <h2>🎬 Dịch &amp; Lồng tiếng</h2>
        <p class="mut">Upload audio/video → tự động STT → tách người nói → dịch → lồng tiếng giữ timing.</p>
        <label>File audio/video (mp3, wav, mp4, mkv… — tối đa 200MB)</label>
        <input type="file" id="dubfile" accept="audio/*,video/*">
        <div class="row">
          <div><label>Ngôn ngữ nguồn</label><select id="srclang"><option value="vi">Tiếng Việt</option><option value="en">English</option></select></div>
          <div><label>Ngôn ngữ đích</label><select id="tgtlang"><option value="en">English</option><option value="vi">Tiếng Việt</option></select></div>
          <div><label>Nền</label><select id="bgmode"><option value="silence">Chỉ giọng dub</option><option value="source_low">Giữ nền gốc nhỏ (karaoke)</option></select></div>
        </div>
        <div class="mut" style="margin-top:10px">Giọng từng nhân vật tự gán theo speaker (Hải Đăng, Mai Anh, Quang Sơn…). Muốn giọng riêng? Tạo ở tab "Giọng của tôi".</div>
        <button class="go" onclick="submitDub()">🚀 Dịch &amp; Lồng tiếng</button>
        <div id="dubmsg" class="status"></div>
      </div>
    </section>

    <!-- TTS -->
    <section id="page-tts" class="page">
      <div class="card">
        <h2>🗣️ Chuyển văn bản thành giọng nói</h2>
        <label>Văn bản</label>
        <textarea id="ttstext" placeholder="Nhập văn bản cần đọc…"></textarea>
        <label>Giọng</label>
        <select id="ttsvoice"><option value="">Mặc định (preset)</option></select>
        <button class="go" onclick="submitTTS()">🗣️ Chuyển thành giọng nói</button>
        <div id="ttsmsg" class="status"></div>
      </div>
    </section>

    <!-- VOICES -->
    <section id="page-voices" class="page">
      <div class="card">
        <h2>🎭 Tạo giọng nói của riêng bạn</h2>
        <p class="mut">Ghi một clip 3–8 giọng rõ ràng (chỉ clone giọng của bạn hoặc có sự đồng ý của chủ giọng).</p>
        <input type="file" id="voicefile" accept="audio/*">
        <label>Tên giọng</label><input id="voicename" placeholder="VD: Giọng của Long">
        <button class="go" onclick="uploadVoice()">⬆️ Tạo voice profile</button>
        <div id="voicemsg" class="status"></div>
        <h3 style="margin-top:20px">Danh sách giọng</h3>
        <div id="voicelist" class="mut">…</div>
      </div>
    </section>

    <!-- STT -->
    <section id="page-stt" class="page">
      <div class="card">
        <h2>📝 Chuyển giọng nói thành văn bản</h2>
        <p class="mut">Xuất SRT có nhãn người nói (SPEAKER_00, SPEAKER_01…).</p>
        <label>File audio/video</label>
        <input type="file" id="sttfile" accept="audio/*,video/*">
        <div class="row"><div><label>Ngôn ngữ</label><select id="sttlang"><option value="vi">Tiếng Việt</option><option value="en">English</option></select></div></div>
        <button class="go" onclick="submitSTT()">📝 Chuyển thành văn bản</button>
        <div id="sttmsg" class="status"></div>
      </div>
    </section>

    <!-- JOBS -->
    <section id="page-jobs" class="page">
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
          <h2>📋 Jobs</h2><button class="ghost" onclick="loadJobs()">Làm mới</button>
        </div>
        <div id="joblist" style="margin-top:12px"></div>
      </div>
    </section>

    <!-- API -->
    <section id="page-api" class="page">
      <div class="card">
        <h2>🔌 API cho nhà phát triển</h2>
        <p class="mut">Chuẩn REST — mọi request gắn header <code>X-API-Key</code>.</p>
        <button class="go" onclick="createKey()">＋ Tạo API key mới</button>
        <div id="keymsg" class="status"></div>
        <table class="keys" style="margin-top:14px"><tbody id="keylist"></tbody></table>
        <h3 style="margin-top:20px">Ví dụ</h3>
<pre>curl -X POST http://&lt;host&gt;/v1/jobs \\
  -H "X-API-Key: yv_..." -H "Content-Type: application/json" \\
  -d '{"type":"dub","media_url":"&lt;media_key&gt;","source_lang":"vi","target_lang":"en"}'</pre>
      </div>
    </section>
  </main>
</div>

<script>
let KEY = localStorage.getItem("yv_api_key") || "";
const $ = (id) => document.getElementById(id);
const H = () => ({ "X-API-Key": KEY, "Content-Type": "application/json" });
const PAGES = ["dashboard","dub","tts","voices","stt","jobs","api"];
let POLL = null;

function esc(s){ const d=document.createElement("div"); d.textContent=s==null?"":String(s); return d.innerHTML; }
function mask(k){ return k ? "••••" + k.slice(-4) : ""; }
function fmt(n){ return (n||0).toLocaleString("vi-VN"); }

function soon(name){ flash("🚧 \"" + name + "\" sắp ra mắt — xem README roadmap.", "err"); }
function flash(msg, cls){ const el = document.querySelector(".page.on .status") || $("gmsg");
  el.className = "status " + (cls||"ok"); el.textContent = msg;
  setTimeout(()=>{ el.textContent=""; }, 4000); }

function go(page) {
  PAGES.forEach(p => { $("page-"+p).classList.toggle("on", p===page); });
  document.querySelectorAll(".nav a[data-page]").forEach(a =>
    a.classList.toggle("on", a.dataset.page === page));
  location.hash = "#/" + page;
  if (page === "dashboard") { refreshMe(); loadDashJobs(); }
  if (page === "jobs") loadJobs();
  if (page === "voices") loadVoices();
  if (page === "api") loadKeys();
  if (window.innerWidth < 920) $("sidebar").style.display = "none";
}
function toggleSide() { const s = $("sidebar");
  s.style.display = (s.style.display === "block") ? "none" : "block"; }

async function enter() {
  KEY = $("gatekey").value.trim();
  const r = await fetch("/v1/me", { headers: H() });
  if (!r.ok) { $("gmsg").textContent = "API key không hợp lệ"; return; }
  localStorage.setItem("yv_api_key", KEY); boot();
}
function logout() { localStorage.removeItem("yv_api_key"); location.reload(); }

async function boot() {
  $("gate").style.display = "none"; $("shell").style.display = "flex";
  $("whokey").textContent = "Key " + mask(KEY);
  const hash = (location.hash || "#/dashboard").replace("#/","");
  go(PAGES.includes(hash) ? hash : "dashboard");
  refreshMe();
  if (POLL) clearInterval(POLL);
  POLL = setInterval(refreshMe, 8000);
}
window.onhashchange = () => { const h=(location.hash||"").replace("#/","");
  if (PAGES.includes(h)) go(h); };

async function refreshMe() {
  const r = await fetch("/v1/me", { headers: H() });
  if (r.status === 401) { logout(); return; }
  const d = await r.json();
  $("top-credits").textContent = fmt(d.credits);
  $("side-free").textContent = fmt(d.credits);
  $("st-free").textContent = fmt(d.credits);
  const sel = $("ttsvoice");
  sel.innerHTML = '<option value="">Mặc định (preset)</option>' +
    d.voices.map(v => `<option value="${esc(v.id)}">${esc(v.name)}</option>`).join("");
  $("voicelist").innerHTML = d.voices.length
    ? d.voices.map(v => `• <b>${esc(v.name)}</b> <span class="mut">(${esc(v.lang)}, ${esc(v.id)})</span>`).join("<br>")
    : "Chưa có giọng nào — upload clip ở trên.";
  loadUsage();
}

async function loadUsage() {
  const r = await fetch("/v1/usage", { headers: H() });
  if (!r.ok) return;
  const d = await r.json();
  const used = d.used, total = Math.max(d.free_quota, used);
  const pct = total ? Math.min(100, used / total * 100) : 0;
  $("donut").setAttribute("stroke-dasharray", (pct/100*302).toFixed(1) + " 302");
  $("donut-used").textContent = fmt(used);
  $("donut-total").textContent = "/ " + fmt(d.free_quota);
  const colors = { tts:"#22c58b", stt:"#38bdf8", translate:"#7c5cff", dub:"#a78bfa", subtitle:"#ffb020" };
  const names = { tts:"TTS", stt:"STT", translate:"Dịch thuật", dub:"Dub video", subtitle:"Phụ đề", other:"Khác" };
  let html = "";
  for (const [t, n] of Object.entries(d.by_type)) {
    const c = colors[t.split("_")[0]] || "#ff8a4c";
    html += `<div><i style="background:${c}"></i>${esc(names[t.split("_")[0]]||t)} — <b>${fmt(n)}</b>
      <div class="usagebar"><i style="width:${total?n/total*100:0}%;background:${c}"></i></div></div>`;
  }
  $("legend").innerHTML = html || '<span class="mut">Chưa sử dụng — tạo job đầu tiên!</span>';
}

async function loadDashJobs() {
  const r = await fetch("/v1/jobs?limit=5", { headers: H() });
  if (!r.ok) return;
  const d = await r.json();
  $("dash-jobs").innerHTML = d.jobs.length
    ? d.jobs.map(j => `<div style="display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--line)">
        <span>${esc(j.type.toUpperCase())} <span class="mut">${esc(j.job_id)}</span></span>
        <span class="pill ${esc(j.status)}">${esc(j.status)}</span></div>`).join("")
    : '<span class="mut">Chưa có dự án nào — bắt đầu ở "Công cụ nhanh"!</span>';
}

async function loadJobs() {
  const r = await fetch("/v1/jobs?limit=20", { headers: H() });
  if (!r.ok) return;
  const d = await r.json();
  const q = ($("q").value || "").toLowerCase();
  const jobs = d.jobs.filter(j => !q || (j.type+j.job_id+j.status).toLowerCase().includes(q));
  $("joblist").innerHTML = jobs.length ? jobs.map(jobHtml).join("")
    : '<span class="mut">Không có job nào khớp.</span>';
}

function jobHtml(j) {
  let media = "";
  if (j.status === "done" && j.result_key) {
    const u = "/media/" + j.result_key + "?api_key=" + encodeURIComponent(KEY);
    if (j.result_key.endsWith(".mp4")) media = `<video controls src="${esc(u)}"></video>`;
    else if (j.result_key.endsWith(".wav")) media = `<audio controls src="${esc(u)}"></audio>`;
    else media = `<a href="${esc(u)}" download>⬇️ Tải kết quả (${esc(j.result_key.split(".").pop())})</a>`;
  }
  const err = j.error ? `<div class="err" style="margin-top:6px">${esc(j.error)}</div>` : "";
  return `<div class="job"><div class="h">
    <b>${esc(j.type.toUpperCase())}</b><span class="mut">${esc(j.job_id)}</span>
    <span class="pill ${esc(j.status)}">${esc(j.status)}${j.status==="running" ? " "+j.progress+"%" : ""}</span></div>
    ${err}${media}</div>`;
}

async function uploadTo(url, inputId, extra) {
  const f = $(inputId).files[0];
  if (!f) throw new Error("chưa chọn file");
  const fd = new FormData(); fd.append("file", f);
  for (const [k,v] of Object.entries(extra||{})) fd.append(k, v);
  const r = await fetch(url, { method:"POST", headers:{ "X-API-Key": KEY }, body: fd });
  const d = await r.json();
  if (!r.ok) throw new Error(d.detail || ("HTTP " + r.status));
  return d;
}

async function submitDub() {
  flash("⏳ đang upload media…");
  try {
    const up = await uploadTo("/v1/media/upload", "dubfile");
    flash("⏳ upload xong — tạo job dub…");
    const r = await fetch("/v1/jobs", { method:"POST", headers:H(), body: JSON.stringify({
      type:"dub", media_url: up.media_key, source_lang: $("srclang").value,
      target_lang: $("tgtlang").value, background_mode: $("bgmode").value }) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.status);
    flash("✔ Job " + d.job_id + " đã tạo (−" + d.credits_charged + " credits). Xem tab Jobs.");
    go("jobs");
  } catch (e) { flash("✗ " + e.message, "err"); }
}

async function submitTTS() {
  flash("⏳ tạo job…");
  try {
    const body = { type:"tts", text: $("ttstext").value };
    if ($("ttsvoice").value) body.voice_id = $("ttsvoice").value;
    const r = await fetch("/v1/jobs", { method:"POST", headers:H(), body: JSON.stringify(body) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.status);
    flash("✔ Job " + d.job_id + " đã tạo (−" + d.credits_charged + " credits).");
    go("jobs");
  } catch (e) { flash("✗ " + e.message, "err"); }
}

async function submitSTT() {
  flash("⏳ tạo job…");
  try {
    const up = await uploadTo("/v1/media/upload", "sttfile");
    const r = await fetch("/v1/jobs", { method:"POST", headers:H(), body: JSON.stringify({
      type:"stt", media_url: up.media_key, source_lang: $("sttlang").value }) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.status);
    flash("✔ Job " + d.job_id + " đã tạo (−" + d.credits_charged + " credits). SRT sẽ hiện ở tab Jobs.");
    go("jobs");
  } catch (e) { flash("✗ " + e.message, "err"); }
}

async function uploadVoice() {
  flash("⏳ upload…");
  try {
    const d = await uploadTo("/v1/voices/upload", "voicefile", { name: $("voicename").value || "Giọng của tôi" });
    flash("✔ Voice profile " + d.voice_id + " đã tạo — clone sẵn sàng.");
    refreshMe();
  } catch (e) { flash("✗ " + e.message, "err"); }
}

async function loadKeys() {
  const r = await fetch("/v1/keys", { headers: H() });
  if (!r.ok) return;
  const d = await r.json();
  $("keylist").innerHTML = d.keys.map(k =>
    `<tr><td><code>${esc(k.key)}</code></td><td>${k.active ? "🟢 active" : "⚪ revoked"}</td>
     <td class="mut">${k.rate_limit_per_min}/phút</td></tr>`).join("")
    || '<tr><td class="mut">Chưa có key nào.</td></tr>';
}
async function createKey() {
  const r = await fetch("/v1/keys", { method:"POST", headers:H() });
  const d = await r.json();
  if (!r.ok) { flash("✗ " + (d.detail||r.status), "err"); return; }
  $("keymsg").innerHTML = '<span class="ok">✔ Key mới (LƯU NGAY — chỉ hiện 1 lần):</span><br><code>' + esc(d.key) + '</code>';
  loadKeys();
}

if (KEY) {
  fetch("/v1/me", { headers: H() }).then(r => { if (r.ok) boot(); else showGate(); });
} else showGate();
function showGate() { $("gate").style.display = ""; $("shell").style.display = "none"; }
</script>
</body></html>"""
