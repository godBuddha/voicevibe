/* YupVox-Clone frontend logic — vanilla JS, no build step.
 * Served via FastAPI StaticFiles mount (/v2). Auth: X-API-Key in
 * localStorage `yv_api_key`; 401 anywhere -> back to the gate.
 */
"use strict";

const KEY = localStorage.getItem("yv_api_key") || "";
const $ = (id) => document.getElementById(id);
const H = () => ({ "X-API-Key": KEY, "Content-Type": "application/json" });

const PANELS = ["dash", "tts", "dub", "voices", "jobs", "pricing"];
const TITLES = {
  dash: "Bảng điều khiển",
  tts: "TTS Studio",
  dub: "Dub video/audio",
  voices: "Giọng của tôi",
  jobs: "Jobs",
  pricing: "Gói dịch vụ & Giá",
};
let POLL = null;

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}
function mask(k) { return k ? "••••" + k.slice(-4) : ""; }
function fmt(n) { return (n || 0).toLocaleString("vi-VN"); }
function setStatus(id, msg, cls) {
  const el = $(id);
  el.className = "status " + (cls || "ok");
  el.textContent = msg;
  setTimeout(() => { el.textContent = ""; }, 4000);
}

/* ---------- navigation ---------- */
function nav(panel) {
  PANELS.forEach((p) => {
    const el = $("p-" + p);
    if (el) el.hidden = p !== panel;
  });
  document.querySelectorAll(".nav a[data-panel]").forEach((a) =>
    a.classList.toggle("on", a.dataset.panel === panel));
  if (TITLES[panel]) $("ptitle").textContent = TITLES[panel];
  if (panel === "dash") { refreshMe(); loadRecent(); }
  if (panel === "voices") refreshMe();
  if (panel === "jobs") loadJobs();
  if (panel === "pricing") loadPricing();
}

function logout() {
  localStorage.removeItem("yv_api_key");
  location.reload();
}

/* ---------- gate / boot ---------- */
async function enter() {
  const k = $("gatekey").value.trim();
  if (!k) { $("gmsg").textContent = "Nhập API key trước"; return; }
  const r = await fetch("/v1/me", { headers: { "X-API-Key": k } });
  if (!r.ok) { $("gmsg").textContent = "API key không hợp lệ"; return; }
  localStorage.setItem("yv_api_key", k);
  location.reload();  // reload with KEY set -> boot()
}

async function refreshMe() {
  const r = await fetch("/v1/me", { headers: H() });
  if (r.status === 401) {
    localStorage.removeItem("yv_api_key");
    $("gate").style.display = "";
    document.querySelector(".main").style.display = "none";
    return;
  }
  const d = await r.json();
  $("credits").textContent = "💰 " + fmt(d.credits) + " credits";
  $("keymask").textContent = "Key " + mask(KEY);
  $("d-credits").textContent = fmt(d.credits);
  $("d-voices").textContent = (d.voices || []).length;
  const sel = $("ttsvoice");
  sel.innerHTML = '<option value="">Mặc định (preset)</option>' +
    (d.voices || []).map(v =>
      `<option value="${esc(v.id)}">${esc(v.name)}</option>`).join("");
  $("voicelist").innerHTML = (d.voices || []).length
    ? d.voices.map(v =>
        `• <b>${esc(v.name)}</b> <span class="mut">(${esc(v.lang)} · ${esc(v.id)})</span>`)
      .join("<br>")
    : '<span class="mut">Chưa có giọng nào — upload clip 3–8s ở trên.</span>';
}

/* ---------- dashboard ---------- */
async function loadRecent() {
  const r = await fetch("/v1/jobs?limit=5", { headers: H() });
  if (!r.ok) return;
  const d = await r.json();
  const done = d.jobs.filter((j) => j.status === "done").length;
  const running = d.jobs.filter((j) => j.status === "running").length;
  $("d-jdone").textContent = done;
  $("d-jrun").textContent = running ? `${running} đang chạy…` : "0 đang chạy";
  $("d-recent").innerHTML = d.jobs.length
    ? d.jobs.map((j) =>
        `<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--line)">
          <span>${esc(j.type.toUpperCase())} <span class="mut">${esc(j.job_id)}</span></span>
          <span class="pill ${esc(j.status)}">${esc(j.status)}</span></div>`).join("")
    : '<span class="mut">Chưa có job nào — bấm "Dub ngay" để bắt đầu!</span>';
}

/* ---------- jobs ---------- */
function jobHtml(j) {
  let media = "";
  if (j.status === "done" && j.result_key) {
    const u = "/media/" + j.result_key + "?api_key=" + encodeURIComponent(KEY);
    if (j.result_key.endsWith(".mp4")) media = `<video controls src="${esc(u)}"></video>`;
    else if (j.result_key.endsWith(".wav")) media = `<audio controls src="${esc(u)}"></audio>`;
    else media = `<a href="${esc(u)}" download>⬇️ Tải kết quả (${esc(j.result_key.split(".").pop())})</a>`;
  }
  const err = j.error ? `<div style="color:var(--err);margin-top:6px">${esc(j.error)}</div>` : "";
  const pr = j.status === "running" ? ` ${j.progress}%` : "";
  return `<div class="job"><div class="h">
    <b>${esc(j.type.toUpperCase())}</b><span class="mut">${esc(j.job_id)}</span>
    <span class="pill ${esc(j.status)}">${esc(j.status)}${pr}</span></div>
    ${err}${media}</div>`;
}

async function loadJobs() {
  const r = await fetch("/v1/jobs?limit=20", { headers: H() });
  if (!r.ok) return;
  const d = await r.json();
  $("joblist").innerHTML = d.jobs.length
    ? d.jobs.map(jobHtml).join("")
    : '<span class="mut">Chưa có job nào.</span>';
}

/* ---------- uploads + jobs ---------- */
async function uploadTo(url, inputId, extra) {
  const f = $(inputId).files[0];
  if (!f) throw new Error("chưa chọn file");
  const fd = new FormData();
  fd.append("file", f);
  for (const [k, v] of Object.entries(extra || {})) fd.append(k, v);
  const r = await fetch(url, { method: "POST", headers: { "X-API-Key": KEY }, body: fd });
  const d = await r.json();
  if (!r.ok) throw new Error(d.detail || ("HTTP " + r.status));
  return d;
}

async function createJob(body) {
  const r = await fetch("/v1/jobs", { method: "POST", headers: H(), body: JSON.stringify(body) });
  const d = await r.json();
  if (!r.ok) throw new Error(d.detail || ("HTTP " + r.status));
  return d;
}

async function submitDub() {
  setStatus("dubmsg", "⏳ đang upload media…");
  try {
    const up = await uploadTo("/v1/media/upload", "dubfile");
    setStatus("dubmsg", "⏳ upload xong — tạo job dub…");
    const d = await createJob({
      type: "dub", media_url: up.media_key,
      source_lang: $("srclang").value, target_lang: $("tgtlang").value,
      background_mode: $("bgmode").value,
    });
    setStatus("dubmsg", "✔ Job " + d.job_id + " đã tạo (−" + d.credits_charged + " credits).");
    nav("jobs");
  } catch (e) { setStatus("dubmsg", "✗ " + e.message, "err"); }
}

async function submitTTS() {
  setStatus("ttsmsg", "⏳ tạo job…");
  try {
    const body = { type: "tts", text: $("ttstext").value };
    if ($("ttsvoice").value) body.voice_id = $("ttsvoice").value;
    const d = await createJob(body);
    setStatus("ttsmsg", "✔ Job " + d.job_id + " đã tạo (−" + d.credits_charged + " credits).");
    nav("jobs");
  } catch (e) { setStatus("ttsmsg", "✗ " + e.message, "err"); }
}

async function uploadVoice() {
  setStatus("voicemsg", "⏳ upload…");
  try {
    const d = await uploadTo("/v1/voices/upload", "voicefile",
      { name: $("voicename").value || "Giọng của tôi" });
    setStatus("voicemsg", "✔ Voice profile " + d.voice_id + " đã tạo — clone sẵn sàng.");
    refreshMe();
  } catch (e) { setStatus("voicemsg", "✗ " + e.message, "err"); }
}

/* ---------- pricing ---------- */
async function loadPricing() {
  const r = await fetch("/v1/pricing", { headers: H() });
  if (!r.ok) return;
  const d = await r.json();
  const names = { tts: "🗣️ TTS", stt: "📝 STT", translate: "🌐 Dịch văn bản",
                  dub: "🎬 Dub video/audio", subtitle: "📄 Dịch phụ đề" };
  $("pricingtable").innerHTML = Object.entries(d.pricing).map(([t, c]) =>
    `<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--line)">
      <span>${esc(names[t] || t)}</span><b>${esc(c)} credits/job</b></div>`).join("");
}

/* ---------- boot ---------- */
if (KEY) {
  fetch("/v1/me", { headers: H() }).then((r) => {
    if (r.ok) {
      refreshMe();
      nav("dash");
      if (POLL) clearInterval(POLL);
      POLL = setInterval(() => {
        refreshMe();
        if (!$("p-jobs").hidden) loadJobs();
        if (!$("p-dash").hidden) loadRecent();
      }, 8000);
    } else {
      localStorage.removeItem("yv_api_key");
      $("gate").style.display = "";
    }
  });
} else {
  $("gate").style.display = "";
}
