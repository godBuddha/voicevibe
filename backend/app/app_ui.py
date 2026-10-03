"""User-facing dashboard UI — bố cục sidebar + topbar theo mẫu SaaS voice.

Single page, vanilla JS, hash routing (#/dashboard, #/dub, #/tts, #/voices,
#/stt, #/jobs, #/api). Không build step — self-host chỉ cần Python.
Usage donut đọc số liệu THẬT từ GET /v1/usage (đếm JOB — self-host miễn phí,
không có hệ thống credit/giá).

Màu sắc KHÔNG hardcode trong file này: mọi token đến từ app/theme.py (sáng + tối),
nên giao diện có chế độ tối mà không cần build step. Xem tests/test_theme.py —
test đó cưỡng chế "không hex ngoài khối token".
"""
from __future__ import annotations

from .theme import THEME_BOOT, THEME_CSS, THEME_JS

APP_HTML = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VoiceVibe — AI Voice cho một thế giới mới</title>
__THEME_BOOT__
<style>
__THEME_CSS__
  * { box-sizing:border-box; }
  body { background:var(--bg); color:var(--fg); font:13.5px/1.5 system-ui,-apple-system,sans-serif; margin:0; }
  a { color:var(--acc); text-decoration:none; }
  h1,h2,h3 { margin:0 0 8px; }
  .mut { color:var(--mut); font-size:12.5px; }

  /* ---- layout ---- */
  #shell { display:flex; min-height:100vh; }
  #sidebar { width:var(--side-w); background:var(--side); border-right:1px solid var(--line);
             padding:12px 10px 10px; display:flex; flex-direction:column; gap:4px;
             position:fixed; top:0; bottom:0; left:0; overflow:hidden; z-index:30; }
  main { margin-left:var(--side-w); flex:1; padding:0 20px 24px; }
  /* Gập sidebar (desktop): toàn bộ hàng ngang nhường cho nội dung —
     trạng thái lưu localStorage, F5 không mất. */
  body.side-hidden #sidebar { display:none; }
  body.side-hidden main { margin-left:0; }
  @media (max-width: 920px) {
    #sidebar { display:none; }
    main { margin-left:0; }
    #burger { display:inline-flex !important; }
  }
  #burger { display:none; background:var(--card); border:1px solid var(--line); color:var(--fg);
            border-radius:8px; padding:6px 10px; cursor:pointer; }
  .icon-btn { background:var(--card); border:1px solid var(--line); color:var(--fg);
              border-radius:8px; width:30px; height:30px; padding:0; cursor:pointer; font-size:14px;
              display:inline-flex; align-items:center; justify-content:center; flex:none; }
  .icon-btn:hover { border-color:var(--acc); }

  /* ---- sidebar ---- */
  .logo { display:flex; gap:8px; align-items:center; padding:2px 6px 10px; }
  .logo .mark { width:28px; height:28px; border-radius:8px; background:linear-gradient(135deg,var(--acc),var(--acc2));
                display:flex; align-items:center; justify-content:center; font-size:14px; }
  .logo b { font-size:14px; } .logo .mut { line-height:1.2; }
  /* nav là phần DUY NHẤT cuộn -> sidecard + liên kết Mã nguồn (AGPL §13) luôn
     ghim ở đáy và nhìn thấy được, dù danh sách menu dài bao nhiêu. */
  .nav { display:flex; flex-direction:column; gap:2px; flex:1; overflow-y:auto; min-height:0; }
  .nav .group { color:var(--mut); font-size:11px; text-transform:uppercase; letter-spacing:.08em;
                padding:8px 8px 3px; }
  .nav a { display:flex; gap:8px; align-items:center; padding:5px 10px; border-radius:8px;
           color:var(--fg); cursor:pointer; font-size:13px; }
  .nav a:hover { background:var(--hover); }
  .nav a.on { background:linear-gradient(90deg,var(--acc),var(--acc2)); color:var(--on-acc); font-weight:600; }
  .nav a.soon { color:var(--mut); opacity:.65; }
  .nav a.soon:hover { background:var(--hover); }
  .sidecard { margin-top:10px; flex:none; background:linear-gradient(160deg,var(--sidecard-from),var(--sidecard-to));
              border:1px solid var(--line); border-radius:12px; padding:10px 12px; font-size:12.5px; }
  .sidecard b { font-size:14px; }
  .sidecard button { width:100%; margin-top:8px; }
  .side-foot { margin-top:10px; padding-top:10px; border-top:1px solid var(--line);
               text-align:center; }
  .side-foot a { font-size:12px; color:var(--mut); }
  .side-foot a:hover { color:var(--acc); }

  /* ---- topbar ---- */
  .topbar { display:flex; gap:10px; align-items:center; padding:12px 0; flex-wrap:wrap; }
  .search { flex:1; min-width:220px; max-width:430px; background:var(--card); border:1px solid var(--line);
            border-radius:8px; padding:7px 12px; display:flex; gap:8px; align-items:center; }
  .search input { border:none; outline:none; background:transparent; width:100%; font:inherit; color:var(--fg); }
  .who { display:flex; gap:9px; align-items:center; }
  .avatar { width:28px; height:28px; border-radius:50%; font-size:12px; background:linear-gradient(135deg,var(--acc),var(--acc2));
            color:var(--on-acc); display:flex; align-items:center; justify-content:center; font-weight:700; }
  .theme-btn { background:var(--card); border:1px solid var(--line); color:var(--fg);
               border-radius:8px; padding:6px 12px; cursor:pointer; font-size:12.5px; white-space:nowrap; }
  .theme-btn:hover { border-color:var(--acc); }

  /* ---- cards / pages ---- */
  .page { display:none; } .page.on { display:block; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }
  .grid2 { display:grid; grid-template-columns: 1.6fr 1fr; gap:12px; margin-top:12px; }
  @media (max-width: 980px) { .grid2 { grid-template-columns:1fr; } }
  /* COMPACT: hero là thanh mảnh một hàng (tiêu đề+desc trái, nút phải) thay khối dày 30px. */
  .hero { background:var(--hero-grad);
          color:var(--on-acc); border-radius:12px; padding:12px 16px;
          display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }
  .hero h1 { font-size:16px; margin:0; } .hero p { opacity:.85; max-width:560px; font-size:12.5px; margin:2px 0 0; }
  .hero button { background:var(--card); color:var(--acc); border:none; border-radius:8px;
                 padding:7px 14px; font-weight:600; cursor:pointer; margin:0; font-size:13px; white-space:nowrap; }
  .statrow { display:flex; gap:12px; flex-wrap:wrap; margin-top:12px; }
  .stat { flex:1; min-width:150px; background:var(--card); border:1px solid var(--line);
          border-radius:12px; padding:10px 14px; }
  .stat b { font-size:16px; display:block; } .stat span { color:var(--mut); font-size:12px; }
  .chips { display:flex; gap:10px; flex-wrap:wrap; margin-top:10px; }
  .chip { background:var(--chip); border:1px solid var(--line); border-radius:8px; padding:7px 12px;
          cursor:pointer; font-size:12.5px; }
  .chip:hover { border-color:var(--acc); }
  label { display:block; color:var(--mut); font-size:12.5px; margin:10px 0 4px; }
  input, select, textarea { background:var(--input); border:1px solid var(--line); color:var(--fg);
          border-radius:8px; padding:8px 10px; width:100%; font:inherit; }
  textarea { min-height:96px; resize:vertical; }
  button.go { background:linear-gradient(90deg,var(--acc),var(--acc2)); border:none; color:var(--on-acc);
              border-radius:8px; padding:8px 18px; font-weight:600; cursor:pointer; margin-top:12px; font-size:13.5px; }
  button.ghost { background:transparent; border:1px solid var(--line); color:var(--mut);
                 border-radius:9px; padding:7px 13px; cursor:pointer; font-size:13px; }
  .row { display:flex; gap:12px; flex-wrap:wrap; } .row > div { flex:1; min-width:170px; }
  .status { margin-top:10px; font-size:13.5px; } .ok { color:var(--ok); } .err { color:var(--err); }
  .job { border:1px solid var(--line); border-radius:10px; padding:10px 12px; margin-bottom:8px; background:var(--card); }
  .job .h { display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap; align-items:center; }
  .pill { font-size:12px; padding:3px 11px; border-radius:99px; }
  .pill.done { background:var(--pill-done-bg); color:var(--ok); }
  .pill.running { background:var(--pill-run-bg); color:var(--pill-run-fg); }
  .pill.failed { background:var(--pill-fail-bg); color:var(--err); }
  .pill.queued { background:var(--pill-queue-bg); color:var(--mut); }
  audio, video { width:100%; margin-top:10px; border-radius:10px; }
  .donut-wrap { display:flex; gap:12px; align-items:center; }
  .legend { font-size:13px; } .legend i { display:inline-block; width:10px; height:10px;
           border-radius:3px; margin-right:7px; }
  .usagebar { height:8px; border-radius:99px; background:var(--track); margin:7px 0; overflow:hidden; }
  .usagebar i { display:block; height:100%; border-radius:99px; }
  table.keys { width:100%; border-collapse:collapse; font-size:13.5px; }
  table.keys td, table.keys th { text-align:left; padding:8px 6px; border-bottom:1px solid var(--line); }
  code { background:var(--code-bg); border-radius:6px; padding:2px 7px; font-size:12.5px; }
  pre { background:var(--pre-bg); color:var(--pre-fg); border-radius:12px; padding:14px; overflow-x:auto; font-size:12.5px; }
  .soonbox { text-align:center; padding:40px 20px; }
  .who .mut { line-height:1.2; }
  .linkbtn { background:transparent; border:1px solid var(--line); color:var(--mut);
             border-radius:9px; padding:6px 12px; cursor:pointer; font-size:13px; }
  .linkbtn:hover { border-color:var(--acc); color:var(--fg); }
  /* Toast dùng chung: mọi thông báo đều hiển thị được, kể cả ở panel không có
     vùng .status riêng (trước đây flash() ghi vào phần tử có thể không tồn tại). */
  #toast { position:fixed; bottom:22px; left:50%; transform:translateX(-50%);
           background:var(--card); border:1px solid var(--line); border-radius:12px;
           padding:12px 20px; font-size:13.5px; box-shadow:0 6px 24px rgba(0,0,0,.14);
           z-index:100; max-width:90vw; display:none; }
  #toast.on { display:block; }
  #toast.ok { border-color:var(--ok); color:var(--ok); }
  #toast.err { border-color:var(--err); color:var(--err); }
</style>
</head>
<body>

<div id="shell">
  <aside id="sidebar">
    <div class="logo"><div class="mark">🎙️</div>
      <div><b>VoiceVibe</b><div class="mut">AI Voice cho một thế giới mới</div></div></div>
    <nav class="nav">
      <a data-page="dashboard" class="on" onclick="go('dashboard')">🏠 Bảng điều khiển</a>
      <div class="group">Tạo nội dung với AI</div>
      <a data-page="tts" onclick="go('tts')">🗣️ Chuyển văn bản thành giọng nói</a>
      <a data-page="tts" onclick="go('tts')">🎚️ TTS Studio</a>
      <a class="soon" onclick="soon('Dịch phụ đề thành giọng nói')">💬 Chuyển phụ đề thành giọng nói</a>
      <a data-page="voices" onclick="go('voices')">🎭 Tạo giọng nói của riêng bạn</a>
      <div class="group">Dịch thuật</div>
      <a class="soon" onclick="soon('Dịch văn bản')">🌐 Dịch văn bản</a>
      <a data-page="subtitle" onclick="go('subtitle')">📄 Dịch phụ đề</a>
      <a data-page="dub" onclick="go('dub')">🔊 Dịch âm thanh</a>
      <a data-page="dub" onclick="go('dub')">🎬 Dịch video</a>
      <div class="group">AI Giọng nói &amp; Video</div>
      <a data-page="stt" onclick="go('stt')">📝 Chuyển giọng nói thành văn bản</a>
      <a data-page="download" onclick="go('download')">⬇️ Tải video từ link</a>
      <a data-page="render" onclick="go('render')">✂️ Xử lý video (phụ đề + 9:16)</a>
      <div class="group">Tóm tắt</div>
      <a data-page="summary" onclick="go('summary')">🗒️ Tóm tắt nội dung</a>
      <a class="soon" onclick="soon('Tạo video bằng AI')">🎥 Tạo video bằng AI</a>
      <a class="soon" onclick="soon('Thay đổi giọng nói')">🎚️ Thay đổi giọng nói</a>
      <div class="group">Khác</div>
      <a data-page="api" onclick="go('api')">🔌 API cho nhà phát triển</a>
      <a data-page="settings" onclick="go('settings')">⚙️ Cài đặt</a>
    </nav>
    <div class="sidecard">
      🚀 Chạy trên hạ tầng của chính bạn — không giới hạn
      <button class="go" onclick="go('dub')">Bắt đầu ngay</button>
      <!-- AGPL-3.0 §13: ứng dụng chạy qua mạng phải chỉ đường lấy mã nguồn.
           Đổi liên kết qua /admin/settings → app.source_url nếu bạn self-host bản sửa. -->
      <div class="side-foot">
        <a href="__SOURCE_URL__" target="_blank" rel="noopener noreferrer">📖 Mã nguồn (AGPL-3.0)</a>
      </div>
    </div>
  </aside>

  <main>
    <div class="topbar">
      <button class="icon-btn" onclick="toggleSide()" title="Ẩn/hiện thanh menu">◧</button>
      <button id="burger" onclick="toggleSide()">☰</button>
      <div class="search">🔍<input id="q" placeholder="Tìm kiếm dự án, giọng nói, công cụ…"></div>
      <button class="theme-btn" data-theme-label onclick="vvToggleTheme()" title="Chuyển chế độ sáng/tối">🌙 Chế độ tối</button>
      <div class="who"><div class="avatar" id="avatar">?</div>
        <div><b id="whoemail">…</b><div class="mut" id="whorole"></div></div></div>
      <button class="linkbtn" onclick="logout()">Đăng xuất</button>
    </div>

    <!-- DASHBOARD -->
    <section id="page-dashboard" class="page on">
      <div class="hero">
        <div>
          <h1>Dịch Audio, Video Online</h1>
          <p>Xóa nhòa cách biệt ngôn ngữ — dịch nhanh với AI, giữ nguyên giọng nhân vật,
             chạy trên hạ tầng của chính bạn.</p>
        </div>
        <button onclick="go('dub')">Bắt đầu ngay →</button>
      </div>
      <div class="statrow">
        <div class="stat"><b id="st-voices">25+</b><span>Giọng đọc AI</span></div>
        <div class="stat"><b>2+</b><span>Ngôn ngữ local</span></div>
        <div class="stat"><b>3–8s</b><span>Clone giọng</span></div>
        <div class="stat"><b id="st-jobs">0</b><span>Job đã xử lý</span></div>
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
          <h3 style="margin-top:14px">Dự án gần đây</h3>
          <div id="dash-jobs" class="mut">…</div>
          <a href="#/jobs" onclick="go('jobs')">Xem tất cả →</a>
        </div>
        <div class="card">
          <h3>Job theo loại</h3>
          <div class="donut-wrap">
            <svg width="120" height="120" viewBox="0 0 120 120">
              <circle cx="60" cy="60" r="48" fill="none" stroke="var(--track)" stroke-width="14"/>
              <circle id="donut" cx="60" cy="60" r="48" fill="none" stroke="var(--acc)"
                      stroke-width="14" stroke-linecap="round"
                      stroke-dasharray="0 302" transform="rotate(-90 60 60)"/>
              <text x="60" y="56" text-anchor="middle" font-size="17" font-weight="700"
                    fill="var(--fg)" id="donut-used">0</text>
              <text x="60" y="74" text-anchor="middle" font-size="10" fill="var(--mut)" id="donut-total">Jobs</text>
            </svg>
            <div class="legend" id="legend">…</div>
          </div>
          <div class="mut" style="margin-top:12px">Số liệu thật theo từng job — cập nhật liên tục.</div>
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
          <div><label>Nền</label><select id="bgmode"><option value="silence">Chỉ giọng dub</option><option value="source_low">Nhạc nền (tách lời bằng AI)</option></select></div>
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

    <!-- SUBTITLE -->
    <section id="page-subtitle" class="page">
      <div class="card">
        <h2>📄 Dịch phụ đề</h2>
        <p class="mut">Nghe file audio/video → phụ đề SRT / VTT / ASS, kèm nhãn người nói.
          Bật song ngữ để có bản gốc ở trên và bản dịch ở dưới.</p>
        <label>File audio/video</label>
        <input type="file" id="subfile" accept="audio/*,video/*">
        <div class="row">
          <div><label>Ngôn ngữ gốc</label><select id="sublang"><option value="vi">Tiếng Việt</option><option value="en">English</option></select></div>
          <div><label>Định dạng</label><select id="subformat"><option value="srt">SRT (phổ biến nhất)</option><option value="vtt">VTT (web)</option><option value="ass">ASS (có kiểu chữ)</option></select></div>
        </div>
        <div class="row">
          <div><label>Dịch sang (bỏ trống = chỉ phiên âm)</label>
            <select id="subtarget"><option value="">— không dịch —</option><option value="en">English</option><option value="vi">Tiếng Việt</option></select></div>
          <div><label>Song ngữ</label>
            <select id="subbilingual"><option value="0">Không</option><option value="1">Có — 2 dòng mỗi câu</option></select></div>
        </div>
        <button class="go" onclick="submitSubtitle()">📄 Tạo phụ đề</button>
        <div id="submsg" class="status"></div>
      </div>
    </section>

    <!-- DOWNLOAD (B1) -->
    <section id="page-download" class="page">
      <div class="card">
        <h2>⬇️ Tải video từ link</h2>
        <p class="mut">Dán link video (YouTube, TikTok…) — hệ tải về kho để dùng lại cho Lồng tiếng / Phụ đề / Tóm tắt. Giới hạn 2 giờ.</p>
        <label>Link video</label>
        <input id="dlurl" placeholder="https://…">
        <div class="row"><div><label>Chất lượng</label>
          <select id="dlq"><option value="1080">1080p</option><option value="720">720p</option><option value="480">480p</option><option value="audio">Chỉ âm thanh (MP3)</option></select></div></div>
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer" title="Tắt: tải ẩn danh (public video tải được, an toàn hơn). Bật: dùng cookies admin đặt ở Cài đặt — bắt buộc với video riêng tư / giới hạn tuổi.">
          <input type="checkbox" id="dlcookies" style="margin:0">
          <span>Dùng cookies đăng nhập (video riêng tư / giới hạn tuổi — mặc định tải ẩn danh)</span></label>
        <button class="go" onclick="submitDownload()">⬇️ Bắt đầu tải</button>
        <div id="dlmsg" class="status"></div>
      </div>
    </section>

    <!-- RENDER (B3+B4) -->
    <section id="page-render" class="page">
      <div class="card">
        <h2>✂️ Xử lý video</h2>
        <p class="mut">In phụ đề song ngữ 2 dòng + cắt dọc 9:16 + banner tiêu đề — gộp một job.</p>
        <label>Video gốc</label>
        <input type="file" id="rfile" accept="video/*">
        <div class="row">
          <div><label>In phụ đề</label><select id="rburn"><option value="0">Không</option><option value="1">Có — 2 dòng song ngữ</option></select></div>
          <div><label>Cắt dọc 9:16</label><select id="rvert"><option value="1">Có (TikTok/Shorts)</option><option value="0">Không</option></select></div>
        </div>
        <div class="row">
          <div><label>File phụ đề (khi bật In phụ đề)</label><input type="file" id="rsub" accept=".srt,.vtt,.ass"></div>
          <div><label>Job phụ đề đã xong (thay file)</label><input id="rjob" placeholder="ID job phụ đề / lồng tiếng"></div>
        </div>
        <div class="row">
          <div><label>Banner dòng chính (vàng lớn)</label><input id="rmajor" placeholder="Tiêu đề chính"></div>
          <div><label>Banner dòng phụ (vàng nhỏ)</label><input id="rminor" placeholder="Tiêu đề phụ"></div>
        </div>
        <button class="go" onclick="submitRender()">✂️ Bắt đầu xử lý</button>
        <div id="rmsg" class="status"></div>
      </div>
    </section>

    <!-- SUMMARY (B6) -->
    <section id="page-summary" class="page">
      <div class="card">
        <h2>🗒️ Tóm tắt nội dung</h2>
        <p class="mut">Dán văn bản HOẶC chọn video/âm thanh (hoặc dán link ở ô dưới) — hệ tự nghe rồi tóm tắt, kèm mốc [giờ:phút:giây].</p>
        <label>Văn bản cần tóm tắt (bỏ trống nếu dùng file/link)</label>
        <textarea id="sumtext" rows="5" placeholder="Dán nội dung…"></textarea>
        <label>Hoặc file video/âm thanh</label>
        <input type="file" id="sumfile" accept="audio/*,video/*">
        <label>Hoặc link video</label>
        <input id="sumurl" placeholder="https://… (tùy chọn)">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer" title="Tắt: tải ẩn danh (public video tải được, an toàn hơn). Bật: dùng cookies admin đặt ở Cài đặt — bắt buộc với video riêng tư / giới hạn tuổi.">
          <input type="checkbox" id="sumcookies" style="margin:0">
          <span>Dùng cookies đăng nhập cho link (video riêng tư / giới hạn tuổi)</span></label>
        <div class="row"><div><label>Tóm tắt bằng</label>
          <select id="sumlang"><option value="vi">Tiếng Việt</option><option value="en">English</option></select></div></div>
        <button class="go" onclick="submitSummary()">🗒️ Tóm tắt ngay</button>
        <div id="summsg" class="status"></div>
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
<pre>curl -X POST http://&lt;host&gt;/v1/jobs \
  -H "X-API-Key: vv_..." -H "Content-Type: application/json" \
  -d '{"type":"dub","media_url":"&lt;media_key&gt;","source_lang":"vi","target_lang":"en"}'</pre>
      </div>
    </section>

    <!-- SETTINGS (hồ sơ + giao diện + thông báo + phiên) -->
    <section id="page-settings" class="page">
      <div class="card">
        <h2>⚙️ Hồ sơ</h2>
        <label class="mut" for="setname">Tên hiển thị</label>
        <div style="display:flex;gap:8px;align-items:center;margin:4px 0 8px">
          <input id="setname" style="max-width:260px" maxlength="120" placeholder="Phần trước @ của email">
          <button class="go" onclick="saveName()">Lưu tên</button>
        </div>
        <div id="setnamemsg" class="status"></div>
        <h3>Đổi mật khẩu</h3>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 8px">
          <input id="setpw0" type="password" placeholder="Mật khẩu hiện tại" style="max-width:180px">
          <input id="setpw1" type="password" placeholder="Mật khẩu mới (≥8 ký tự)" style="max-width:180px">
          <button class="go" onclick="changePw()">Đổi mật khẩu</button>
        </div>
        <div id="setpwmsg" class="status"></div>
        <p class="mut">Đổi xong, mọi thiết bị KHÁC bị đăng xuất; thiết bị này giữ nguyên.</p>
      </div>

      <div class="card">
        <h2>🔔 Thông báo job hoàn thành</h2>
        <p class="mut">Thông báo trình duyệt khi job xong (chỉ khi tab còn mở). Tắt thì không tốn yêu cầu nào.</p>
        <button id="notifybtn" class="go" onclick="toggleNotify()">Bật thông báo</button>
        <div id="notifymsg" class="status"></div>
      </div>

      <div class="card">
        <h2>🖥️ Phiên đăng nhập</h2>
        <p class="mut">Thiết bị nào đang đăng nhập bằng tài khoản của bạn.</p>
        <button class="go" onclick="revokeOthers()">Đăng xuất mọi thiết bị khác</button>
        <div id="sessmsg" class="status"></div>
        <table class="keys" style="margin-top:10px"><tbody id="sesslist"></tbody></table>
      </div>
    </section>
  </main>
</div>
<div id="toast"></div>

<script>
__THEME_JS__
const $ = (id) => document.getElementById(id);
// Xác thực qua COOKIE PHIÊN do server đặt (HttpOnly) — JS không đọc/không lưu token.
// `credentials:"same-origin"` để fetch gửi kèm cookie.
const H = () => ({ "Content-Type": "application/json" });
const PAGES = ["dashboard","dub","tts","voices","stt","subtitle","jobs","api","settings","download","render","summary"];
let POLL = null, ME = {};

function esc(s){ const d=document.createElement("div"); d.textContent=s==null?"":String(s); return d.innerHTML; }
function fmt(n){ return (n||0).toLocaleString("vi-VN"); }

function soon(name){ flash('🚧 "' + name + '" sắp ra mắt — xem README roadmap.', "err"); }
function flash(msg, cls){ const el = $("toast");
  el.className = "on " + (cls||"ok"); el.textContent = msg;
  clearTimeout(window._toastT);
  window._toastT = setTimeout(()=>{ el.className = ""; el.textContent = ""; }, 4000); }

function go(page) {
  PAGES.forEach(p => { $("page-"+p).classList.toggle("on", p===page); });
  document.querySelectorAll(".nav a[data-page]").forEach(a =>
    a.classList.toggle("on", a.dataset.page === page));
  location.hash = "#/" + page;
  if (page === "dashboard") { refreshMe(); loadDashJobs(); }
  if (page === "jobs") loadJobs();
  if (page === "voices") refreshMe();  // refreshMe() renders the voice list too
  if (page === "api") loadKeys();
  if (page === "settings") loadSettingsPage();
  if (window.innerWidth < 920) $("sidebar").style.display = "none";
}
function toggleSide() {
  if (window.innerWidth < 920) {  // mobile: media query đã ẩn sẵn, burger = hiện tạm
    const s = $("sidebar");
    s.style.display = (s.style.display === "block") ? "none" : "block";
    return;
  }
  // Desktop: gập HOÀN TOÀN, ghi nhớ lựa chọn qua F5 (giống SPA — vv_side_hidden)
  const hidden = document.body.classList.toggle("side-hidden");
  try { localStorage.setItem("vv_side_hidden", hidden ? "1" : "0"); } catch (e) {}
}

// Phiên hết hạn / chưa đăng nhập -> để server quyết định, không tự đoán.
function needLogin() { location.href = "/login?next=" + encodeURIComponent(location.pathname + location.hash); }

async function logout() {
  try { await fetch("/v1/auth/logout", { method:"POST", credentials:"same-origin" }); } catch (e) {}
  location.href = "/login";
}

async function boot() {
  // Khôi phục lựa chọn "ẩn thanh menu" của phiên trước (desktop only — mobile
  // vốn ẩn sẵn bằng media query, class sẽ không có tác dụng gì thêm).
  try {
    if (localStorage.getItem("vv_side_hidden") === "1" && window.innerWidth >= 920) {
      document.body.classList.add("side-hidden");
    }
  } catch (e) {}
  const hash = (location.hash || "#/dashboard").replace("#/","");
  go(PAGES.includes(hash) ? hash : "dashboard");
  refreshMe();
  if (POLL) clearInterval(POLL);
  POLL = setInterval(refreshMe, 8000);
}
window.onhashchange = () => { const h=(location.hash||"").replace("#/","");
  if (PAGES.includes(h)) go(h); };

async function refreshMe() {
  const r = await fetch("/v1/me", { headers: H(), credentials: "same-origin" });
  if (r.status === 401) { needLogin(); return; }
  const d = await r.json();
  ME = d;
  $("whoemail").textContent = d.email || "";
  $("avatar").textContent = (d.email || "?").charAt(0).toUpperCase();
  $("whorole").textContent = d.role === "admin" ? "Quản trị viên" : "Người dùng";
  const sel = $("ttsvoice");
  sel.innerHTML = '<option value="">Mặc định (preset)</option>' +
    (d.voices || []).map(v => `<option value="${esc(v.id)}">${esc(v.name)}</option>`).join("");
  $("voicelist").innerHTML = (d.voices || []).length
    ? d.voices.map(v => `• <b>${esc(v.name)}</b> <span class="mut">(${esc(v.lang)}, ${esc(v.id)})</span>`).join("<br>")
    : "Chưa có giọng nào — upload clip ở trên.";
  loadUsage();
}

async function loadUsage() {
  const r = await fetch("/v1/usage", { headers: H(), credentials: "same-origin" });
  if (!r.ok) return;
  const d = await r.json();
  const total = d.total_jobs || 0;
  // Donut = share số job theo loại (không có hạn mức — self-host miễn phí).
  $("donut").setAttribute("stroke-dasharray", (total ? Math.min(302, 302*0.999) : 0).toFixed(1) + " 302");
  $("donut-used").textContent = fmt(total);
  $("st-jobs").textContent = fmt(total);
  // Màu đọc từ CSS var -> tự đổi theo theme (không hardcode hex ở đây).
  const colors = chartColors();
  const names = { tts:"TTS", stt:"STT", translate:"Dịch thuật", dub:"Dub video", subtitle:"Phụ đề", download:"Tải video", render:"Xử lý video", summary:"Tóm tắt", other:"Khác" };
  let html = "";
  for (const [t, n] of Object.entries(d.by_type)) {
    const c = colors[t.split("_")[0]] || vvCssVar("--chart-other");
    html += `<div><i style="background:${c}"></i>${esc(names[t.split("_")[0]]||t)} — <b>${fmt(n)} job</b>
      <div class="usagebar"><i style="width:${total?n/total*100:0}%;background:${c}"></i></div></div>`;
  }
  $("legend").innerHTML = html || '<span class="mut">Chưa có job nào — tạo job đầu tiên!</span>';
}

function chartColors() {
  return { tts:vvCssVar("--chart-tts"), stt:vvCssVar("--chart-stt"),
           translate:vvCssVar("--chart-translate"), dub:vvCssVar("--chart-dub"),
           subtitle:vvCssVar("--chart-subtitle") };
}

// Đổi theme -> vẽ lại donut/legend để lấy màu mới.
vvOnThemeChange(loadUsage);

async function loadDashJobs() {
  const r = await fetch("/v1/jobs?limit=5", { headers: H(), credentials: "same-origin" });
  if (!r.ok) return;
  const d = await r.json();
  $("dash-jobs").innerHTML = d.jobs.length
    ? d.jobs.map(j => `<div style="display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--line)">
        <span>${esc(j.type.toUpperCase())} <span class="mut">${esc(j.job_id)}</span></span>
        <span class="pill ${esc(j.status)}">${esc(j.status)}</span></div>`).join("")
    : '<span class="mut">Chưa có dự án nào — bắt đầu ở "Công cụ nhanh"!</span>';
  notifyJobDone(d.jobs);  // pref vv_notify=1: bắn Notification khi job chuyển trạng thái
}

async function loadJobs() {
  const r = await fetch("/v1/jobs?limit=20", { headers: H(), credentials: "same-origin" });
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
    const u = "/media/" + j.result_key;
    if (j.result_key.endsWith(".mp4")) media = `<video controls src="${esc(u)}"></video>`;
    else if (j.result_key.endsWith(".wav")) media = `<audio controls src="${esc(u)}"></audio>`;
    else media = `<a href="${esc(u)}" download>⬇️ Tải kết quả (${esc(j.result_key.split(".").pop())})</a>`;
  }
  const err = j.error ? `<div class="err" style="margin-top:6px">${esc(j.error)}</div>` : "";
  // Tiến độ theo CÔNG ĐOẠN (backend ghi params.stage mỗi khâu) — thấy "nghe
  // đoạn 2/5" thay vì chỉ số % trơn.
  const stg = (j.params && j.params.stage && (j.status === "running" || j.status === "queued"))
    ? `<span class="mut" style="margin-left:6px">— ${esc(j.params.stage)}</span>` : "";
  // Hành động: Hủy (còn hoạt động) / Chạy lại (hỏng hoặc đã hủy — tiếp tục từ
  // công đoạn đã xong nhờ sổ tay công đoạn, không nấu lại từ đầu).
  const act = (j.status === "queued" || j.status === "running")
    ? `<button class="ghost" onclick="cancelJob('${j.job_id}')">✕ Hủy</button>`
    : ((j.status === "failed" || j.status === "cancelled")
       ? `<button class="ghost" onclick="retryJob('${j.job_id}')" title="Tiếp tục từ công đoạn đã xong">↻ Chạy lại</button>` : "");
  return `<div class="job"><div class="h">
    <b>${esc(j.type.toUpperCase())}</b><span class="mut">${esc(j.job_id)}</span>
    <span class="pill ${esc(j.status)}">${esc(j.status)}${j.status==="running" ? " "+j.progress+"%" : ""}</span>
    ${stg}${act ? `<span style="margin-left:auto">${act}</span>` : ""}</div>
    ${err}${media}</div>`;
}

async function cancelJob(id) {
  if (!confirm("Hủy job này? Job đang chờ/xử lý sẽ bị dừng.")) return;
  const r = await fetch("/v1/jobs/" + id + "/cancel", { method: "POST", headers: H(), credentials: "same-origin" });
  const d = await r.json();
  if (!r.ok) { flash("✗ " + (d.detail || r.status), "err"); return; }
  flash("✔ Đã hủy job " + id);
  loadJobs();
}

async function retryJob(id) {
  // Chạy lại = xếp hàng lại; khâu nào đã xong (sổ tay công đoạn) sẽ bị BỎ QUA.
  const r = await fetch("/v1/jobs/" + id + "/retry", { method: "POST", headers: H(), credentials: "same-origin" });
  const d = await r.json();
  if (!r.ok) { flash("✗ " + (d.detail || r.status), "err"); return; }
  flash("✔ Đã xếp hàng lại job " + id + " — tiếp tục từ công đoạn đã xong");
  loadJobs();
}

async function uploadTo(url, inputId, extra) {
  const f = $(inputId).files[0];
  if (!f) throw new Error("chưa chọn file");
  const fd = new FormData(); fd.append("file", f);
  for (const [k,v] of Object.entries(extra||{})) fd.append(k, v);
  const r = await fetch(url, { method:"POST", credentials:"same-origin", body: fd });
  const d = await r.json();
  if (!r.ok) throw new Error(d.detail || ("HTTP " + r.status));
  return d;
}

async function submitDub() {
  flash("⏳ đang upload media…");
  try {
    const up = await uploadTo("/v1/media/upload", "dubfile");
    flash("⏳ upload xong — tạo job dub…");
    const r = await fetch("/v1/jobs", { method:"POST", headers:H(), credentials:"same-origin", body: JSON.stringify({
      type:"dub", media_url: up.media_key, source_lang: $("srclang").value,
      target_lang: $("tgtlang").value, background_mode: $("bgmode").value }) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.status);
    flash("✔ Job " + d.job_id + " đã tạo. Xem tab Jobs.");
    go("jobs");
  } catch (e) { flash("✗ " + e.message, "err"); }
}

async function submitTTS() {
  flash("⏳ tạo job…");
  try {
    const body = { type:"tts", text: $("ttstext").value };
    if ($("ttsvoice").value) body.voice_id = $("ttsvoice").value;
    const r = await fetch("/v1/jobs", { method:"POST", headers:H(), credentials:"same-origin", body: JSON.stringify(body) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.status);
    flash("✔ Job " + d.job_id + " đã tạo.");
    go("jobs");
  } catch (e) { flash("✗ " + e.message, "err"); }
}

async function submitSTT() {
  flash("⏳ tạo job…");
  try {
    const up = await uploadTo("/v1/media/upload", "sttfile");
    const r = await fetch("/v1/jobs", { method:"POST", headers:H(), credentials:"same-origin", body: JSON.stringify({
      type:"stt", media_url: up.media_key, source_lang: $("sttlang").value }) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.status);
    flash("✔ Job " + d.job_id + " đã tạo. SRT sẽ hiện ở tab Jobs.");
    go("jobs");
  } catch (e) { flash("✗ " + e.message, "err"); }
}

async function submitDownload() {
  flash("⏳ tạo job tải video…");
  try {
    const r = await fetch("/v1/jobs", { method:"POST", headers:H(), credentials:"same-origin", body: JSON.stringify({
      type:"download", source_url: $("dlurl").value.trim(), quality: $("dlq").value,
      use_cookies: $("dlcookies").checked }) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.status);
    flash("✔ Job " + d.job_id + " đã tạo — theo dõi ở tab Jobs.");
    go("jobs");
  } catch (e) { flash("✗ " + e.message, "err"); }
}

async function submitRender() {
  flash("⏳ tạo job xử lý video…");
  try {
    const up = $("rfile").files[0] ? await uploadTo("/v1/media/upload", "rfile") : null;
    const body = { type:"render",
      burn_subtitles: $("rburn").value === "1",
      vertical: $("rvert").value === "1" };
    if (up) body.media_url = up.media_key;
    if ($("rburn").value === "1") {
      const sub = $("rsub").files[0] ? await uploadTo("/v1/media/upload", "rsub") : null;
      if (sub) body.subtitle_key = sub.media_key;
      else if ($("rjob").value.trim()) body.subtitle_job_id = $("rjob").value.trim();
      else throw new Error("In phụ đề cần file phụ đề hoặc ID job phụ đề đã xong");
    }
    const major = $("rmajor").value.trim(), minor = $("rminor").value.trim();
    if (major || minor) body.banner = { major: major, minor: minor };
    const r = await fetch("/v1/jobs", { method:"POST", headers:H(), credentials:"same-origin", body: JSON.stringify(body) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.status);
    flash("✔ Job " + d.job_id + " đã tạo — theo dõi ở tab Jobs.");
    go("jobs");
  } catch (e) { flash("✗ " + e.message, "err"); }
}

async function submitSummary() {
  flash("⏳ tạo job tóm tắt…");
  try {
    const body = { type:"summary", target_lang: $("sumlang").value,
                   use_cookies: $("sumcookies").checked };
    if ($("sumtext").value.trim()) body.text = $("sumtext").value;
    else if ($("sumurl").value.trim()) body.source_url = $("sumurl").value.trim();
    else if ($("sumfile").files[0]) {
      const up = await uploadTo("/v1/media/upload", "sumfile");
      body.media_url = up.media_key;
    } else throw new Error("Nhập văn bản, chọn file hoặc dán link");
    const r = await fetch("/v1/jobs", { method:"POST", headers:H(), credentials:"same-origin", body: JSON.stringify(body) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.status);
    flash("✔ Job " + d.job_id + " đã tạo — kết quả ở tab Jobs.");
    go("jobs");
  } catch (e) { flash("✗ " + e.message, "err"); }
}

async function submitSubtitle() {
  flash("⏳ tạo job phụ đề…");
  try {
    const up = await uploadTo("/v1/media/upload", "subfile");
    const target = $("subtarget").value;
    const body = {
      type: "subtitle", media_url: up.media_key,
      source_lang: $("sublang").value,
      format: $("subformat").value,
      bilingual: $("subbilingual").value === "1",
    };
    if (target) body.target_lang = target;
    const r = await fetch("/v1/jobs", { method:"POST", headers:H(), credentials:"same-origin", body: JSON.stringify(body) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.status);
    flash("✔ Job " + d.job_id + " đã tạo. Phụ đề sẽ hiện ở tab Jobs.");
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
  const r = await fetch("/v1/keys", { headers: H(), credentials: "same-origin" });
  if (!r.ok) return;
  const d = await r.json();
  $("keylist").innerHTML = d.keys.map(k =>
    `<tr><td><code>${esc(k.key)}</code></td><td>${k.active ? "🟢 active" : "⚪ revoked"}</td>
     <td class="mut">${k.rate_limit_per_min}/phút</td></tr>`).join("")
    || '<tr><td class="mut">Chưa có key nào.</td></tr>';
}
async function createKey() {
  const r = await fetch("/v1/keys", { method:"POST", headers:H(), credentials:"same-origin" });
  const d = await r.json();
  if (!r.ok) { flash("✗ " + (d.detail||r.status), "err"); return; }
  $("keymsg").innerHTML = '<span class="ok">✔ Key mới (LƯU NGAY — chỉ hiện 1 lần):</span><br><code>' + esc(d.key) + '</code>';
  loadKeys();
}

// ------------------------------------------------ Settings (hồ sơ/phiên/thông báo)
async function loadSettingsPage() {
  if (ME && ME.email) $("setname").value = ME.name || "";
  toggleNotifyLabel();
  loadSessions();
}

async function saveName() {
  const name = $("setname").value.trim();
  const r = await fetch("/v1/me", { method:"PATCH", headers:H(), credentials:"same-origin",
    body: JSON.stringify({ name }) });
  const d = await r.json();
  $("setnamemsg").innerHTML = r.ok
    ? '<span class="ok">✔ Đã lưu tên hiển thị.</span>'
    : '<span class="err">✗ ' + esc(d.detail || r.status) + '</span>';
  if (r.ok) { ME.name = d.name; $("whoemail").textContent = d.name || d.email; }
}

async function changePw() {
  const r = await fetch("/v1/me/password", { method:"POST", headers:H(), credentials:"same-origin",
    body: JSON.stringify({ current_password: $("setpw0").value, new_password: $("setpw1").value }) });
  const d = await r.json();
  // 403 = sai mật khẩu hiện tại (KHÔNG phải hết phiên) — hiện inline, không đá về login.
  $("setpwmsg").innerHTML = r.ok
    ? '<span class="ok">✔ Đã đổi mật khẩu' + (d.sessions_revoked ? ' — ' + d.sessions_revoked + ' phiên khác đã đăng xuất' : '') + '.</span>'
    : '<span class="err">✗ ' + esc(d.detail || r.status) + '</span>';
  if (r.ok) { $("setpw0").value = ""; $("setpw1").value = ""; }
}

function toggleNotifyLabel() {
  let on = false;
  try { on = localStorage.getItem("vv_notify") === "1"; } catch (e) {}
  $("notifybtn").textContent = on ? "Tắt thông báo" : "Bật thông báo";
}

async function toggleNotify() {
  if (typeof Notification === "undefined") {
    $("notifymsg").innerHTML = '<span class="err">✗ Trình duyệt không hỗ trợ thông báo.</span>'; return;
  }
  let on = false;
  try { on = localStorage.getItem("vv_notify") === "1"; } catch (e) {}
  if (on) {
    try { localStorage.setItem("vv_notify", "0"); } catch (e) {}
    toggleNotifyLabel();
    $("notifymsg").innerHTML = '<span class="ok">Đã tắt.</span>';
    return;
  }
  let perm = Notification.permission;
  if (perm === "default") perm = await Notification.requestPermission();
  if (perm !== "granted") {
    $("notifymsg").innerHTML = '<span class="err">✗ Bạn đã chặn thông báo trong trình duyệt.</span>';
    return;
  }
  try { localStorage.setItem("vv_notify", "1"); } catch (e) {}
  toggleNotifyLabel();
  $("notifymsg").innerHTML = '<span class="ok">✔ Đã bật — job hoàn thành sẽ hiện thông báo.</span>';
}

async function loadSessions() {
  const r = await fetch("/v1/me/sessions", { credentials: "same-origin" });
  if (!r.ok) return;
  const d = await r.json();
  const cur = d.current;
  $("sesslist").innerHTML = (d.sessions || []).map(s => {
    const when = s.last_seen_at ? new Date(s.last_seen_at * 1000).toLocaleString("vi-VN") : "—";
    const dev = s.current ? "Thiết bị này" : esc(s.user_agent ? s.user_agent.split(" ")[0].slice(0, 18) : "Không rõ");
    const btn = s.current ? '<span class="mut">đang dùng</span>'
      : '<button class="mini" onclick="revokeSession(\'' + s.token_hash + '\')">Thu hồi</button>';
    return '<tr><td>' + dev + '</td><td class="mut">' + esc(s.ip || "—") + '</td><td class="mut">' + when + '</td><td>' + btn + '</td></tr>';
  }).join("") || '<tr><td class="mut">Không có phiên nào.</td></tr>';
}

async function revokeSession(hash) {
  const r = await fetch("/v1/me/sessions/" + hash, { method:"DELETE", credentials:"same-origin" });
  if (r.ok) { flash("✔ Đã đăng xuất thiết bị đó."); loadSessions(); }
  else flash("✗ " + ((await r.json()).detail || r.status), "err");
}

async function revokeOthers() {
  const r = await fetch("/v1/me/sessions", { method:"DELETE", credentials:"same-origin" });
  const d = await r.json();
  if (r.ok) { flash("✔ Đã đăng xuất " + d.revoked + " thiết bị khác."); loadSessions(); }
  else flash("✗ " + (d.detail || r.status), "err");
}

// Thông báo khi job CHUYỂN trạng thái (đang chạy → xong/thất bại) — so trạng
// thái cũ của loadDashJobs, chỉ bắn khi pref bật (vv_notify=1) + đã được phép.
let _prevJobStatus = {};
function notifyJobDone(list) {
  let allowed = false;
  try { allowed = localStorage.getItem("vv_notify") === "1"; } catch (e) {}
  if (!allowed || typeof Notification === "undefined" || Notification.permission !== "granted") return;
  (list || []).forEach(j => {
    const before = _prevJobStatus[j.job_id];
    if (before && before !== j.status && (j.status === "done" || j.status === "failed")) {
      const label = j.status === "done" ? "hoàn thành" : "thất bại";
      try { new Notification("VoiceVibe — job " + label, { body: String((j.params && (j.params.media_url || j.params.text)) || j.type).slice(0, 60) }); } catch (e) {}
    }
    _prevJobStatus[j.job_id] = j.status;
  });
}

// Server chỉ trả trang này khi đã có phiên hợp lệ, nên không cần gate ở client nữa.
// Vẫn kiểm tra một lần để nếu phiên vừa hết hạn thì chuyển về /login ngay.
fetch("/v1/me", { headers: H(), credentials: "same-origin" })
  .then(r => { if (r.ok) boot(); else needLogin(); })
  .catch(() => needLogin());

vvThemeChanged();  // đồng bộ nhãn nút sáng/tối với theme đã áp ở <head>
</script>
</body></html>"""

# Nội suy token theme (không dùng f-string: CSS/JS đầy dấu ngoặc nhọn).
APP_HTML = (APP_HTML
            .replace("__THEME_BOOT__", THEME_BOOT)
            .replace("__THEME_CSS__", THEME_CSS)
            .replace("__THEME_JS__", THEME_JS))
