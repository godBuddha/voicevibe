# Mã nguồn OSS tham chiếu — đối chiếu tính năng trong ảnh mẫu

Tài liệu này là kết quả rà soát **các dự án mã nguồn mở có chức năng tương tự ảnh mẫu
giao diện** (`docs/design-mockup.jpeg` — sản phẩm proprietary, không public mã nguồn),
mục đích: **học kiến trúc + tái sử dụng code** cho YupVox-Clone.

**Mọi license dưới đây đã được XÁC MINH bằng cách fetch file `LICENSE` thật của repo
(hay GitHub/HuggingFace API), ngày 27/09/2026 — không lấy từ trí nhớ.**
Stars/chỉ số là ước lượng cùng ngày.

## 0. Nguyên tắc bắt buộc (dự án này là Apache-2.0)

| Loại license | Được copy code? | Lý do |
|---|---|---|
| MIT / Apache-2.0 / BSD-2 / BSD-3 / ISC | ✅ **ĐƯỢC** | Permissive — phải **giữ nguyên copyright notice** + ghi công (NOTICE) |
| MPL-2.0 / LGPL-3.0 | ⚠️ Hạn chế | Dùng như **thư viện riêng, không sửa** thì OK; sửa rồi nhúng vào là phải mở source phần đó |
| **AGPL-3.0** | ❌ **KHÔNG** | Network copyleft: chạy như *dịch vụ qua mạng* → buộc mở source **toàn bộ** hệ thống |
| **GPL-3.0 / SSPL** | ❌ **KHÔNG** | Copyleft lây nhiễm khi link/nhúng |
| License riêng (research/community license) | ❌ Phải đọc điều khoản | Thường cấm thương mại, hoặc giới hạn doanh thu/khu vực |

> ⚠️ **Bẫy phổ biến nhất — đã xác minh nhiều lần:** repo **code permissive** nhưng
> **trọng số model (weights) lại non-commercial**. Copy code được, nhưng **không được
> ship weights**. Luôn kiểm license của *weights* trên HuggingFace, không chỉ repo.

## 1. Đối chiếu tính năng trong ảnh mẫu → dự án OSS

### 1.1 Dubbing / giữ nguyên giọng nhân vật / nhạc nền

| Tính năng (mockup) | Dự án tham chiếu | License (đã verify) | Hành động | Ghi chú |
|---|---|---|---|---|
| Pipeline dub đầu-cuối | **YouDub-webui** `liuzhao1225/YouDub-webui` | **Apache-2.0** | 🟢 **ADOPT kiến trúc** | Gần nhất với hệ thống của ta: yt-dlp → Demucs tách vocal/bed → Whisper word-ts → dịch → TTS → mux. Có sẵn: chia chunk Demucs, ghi `.pending`→publish atomic, override device từng stage, xử lý RF64 cho audio dài |
| Chia/khớp lại phụ đề theo timing | **VideoLingo** `Huanshere/VideoLingo` | **Apache-2.0** | 🟢 **ADOPT thuật toán** | Chuẩn "Netflix-grade": re-segmentation + timing-fit của họ chính là thứ engine `needs_shorter_text` của ta đang thiếu vòng lặp thực thi |
| **Track "Nhạc nền"** (mockup có hẳn track riêng) | **Demucs v4** `facebookresearch/demucs` (`--two-stems=vocals`) | **MIT** | 🟢 **ADOPT — gap lớn nhất** | Ta đang dùng `silence`/`source_low` (hạ âm gốc 12%); tách stem thật = giữ nguyên nhạc nền, chỉ thay vocal → đúng trải nghiệm mockup |
| Tách stem dạng thư viện/server | **python-audio-separator** `nomadkaraoke/python-audio-separator` | **MIT** | 🟢 ADOPT (tùy chọn) | Wrapper MDX-Net/Demucs, dễ gắn vào worker |
| Lip-sync (nhép miệng theo giọng dub) | **MuseTalk** `TMElyralab/MuseTalk` | **MIT** (code + weights) | 🟢 ADOPT nếu làm | Sạch license nhất, ~realtime trên 30xx, 4–8GB VRAM |
| Lip-sync (mới, Apache) | **X-Dub** `KlingAIResearch/X-Dub` | **Apache-2.0** (code + weights) | 🟡 Theo dõi | Mới (2026-03), mask-free visual dubbing |
| Lip-sync ảnh tĩnh | **SadTalker** `OpenTalker/SadTalker` | **Apache-2.0** | 🟡 Theo dõi | Repo đã ngừng (2024-06) |
| Dub có tách giọng | **SoniTranslate** `R3gm/SoniTranslate`, **asmr-dubber** `EveningStudy/asmr-dubber` (MIT) | Apache-2.0 / MIT | 🟡 Tham khảo | SoniTranslate: code OK nhưng weights pyannote bị gated |
| Chuyển phụ đề thành giọng nói | **edge-tts** `edge_tts/srt_composer.py` | **MIT** (riêng file này; phần còn lại LGPL) | 🟡 Học logic timing | ⚠️ Là wrapper cho service Microsoft Edge (rủi ro ToS), ta đã có TTS riêng — chỉ nên học cách đặt audio theo cue |
| Ép timing subtitle vào audio | **ffsubsync** `smacke/ffsubsync` | **MIT** | 🟢 ADOPT | Retime phụ đề lên audio **đã dub** (sau khi TTS làm lệch timing) |

### 1.2 TTS / clone giọng / đổi giọng

| Tính năng (mockup) | Dự án | License (verified) | Hành động | Ghi chú |
|---|---|---|---|---|
| TTS tiếng Việt + clone (đang dùng) | **VieNeu-TTS v3 Turbo** `pnnbao97/VieNeu-TTS` | **Apache-2.0** (code + weights) | ✅ Đang dùng — **xác nhận lựa chọn đúng** | ~2.7k★, active; CPU GGUF được, RTF ~0.01–0.02 trên RTX 3060 |
| TTS tiếng Việt thay thế | **VietVoice-TTS** `nguyenvulebinh/VietVoice-TTS`, **ZeroTTS** `zeroweight-ai/ZeroTTS` | **MIT** (code + weights) | 🟢 Dự phòng | Cả hai đều permissive → có phương án B nếu VieNeu v3 có vấn đề |
| Clone 5s chất lượng cao, cộng đồng lớn | **GPT-SoVITS** `RVC-Boss/GPT-SoVITS` | **MIT** (code + weights đều MIT) | 🟢 Dự phòng mạnh | 62k★; có sẵn API server; cộng đồng model tiếng Việt lớn |
| **Thay đổi giọng nói** (mockup có) | **RVC WebUI** / **Applio** `IAHispano/Applio` | **MIT** (code + pretrained mặc định) | 🟢 ADOPT khi làm | Chuẩn de-facto; Applio có HTTP API + realtime, fork dễ dùng hơn |
| Đổi giọng zero-shot (không cần train) | **OpenVoice v2** `myshell-ai/OpenVoice` | **MIT** (code + weights) | 🟢 ADOPT | Chuyển timbre tách khỏi ngôn ngữ — hợp tính năng "voice changer" |
| Đổi giọng realtime | **w-okada/voice-changer (VCClient)** | **MIT** | 🟡 Tham khảo | Protocol audio server realtime + registry đổi model |
| TTS server chuẩn OpenAI | **speaches** `speaches-ai/speaches` (MIT), **Kokoro-FastAPI** `remsky/Kokoro-FastAPI` (**Apache-2.0**) | MIT / Apache-2.0 | 🟡 Học spec | Ta đã có `/v1/audio/speech` ingress; học thêm: batched inference + streaming chunker + "voice = mix có trọng số" |
| Chunker streaming | **RealtimeTTS** `KoljaB/RealtimeTTS` | **MIT** | 🟢 ADOPT (nhỏ) | Tách câu → stream, độc lập backend |
| Emotion/style tags | **Orpheus-TTS** (Apache-2.0 code), **Chatterbox** (MIT), **Zonos** (Apache-2.0) | — | 🟡 Học grammar | Mockup không nêu nhưng là điểm khác biệt; VieNeu đã có emotion control |

### 1.3 STT / tách người nói / phụ đề

| Tính năng (mockup) | Dự án | License (verified) | Hành động | Ghi chú |
|---|---|---|---|---|
| STT (đang dùng) | **faster-whisper** `SYSTRAN/faster-whisper` | **MIT** (weights large-v3 Apache-2.0) | ✅ Đang dùng | Bổ sung ngay: **bộ chống hallucination** (`condition_on_previous_text=False`, `no_speech_threshold`, `log_prob_threshold`, `compression_ratio_threshold`) + `BatchedInferencePipeline` |
| STT tiếng Việt chuyên biệt | **PhoWhisper** `VinAIResearch/PhoWhisper` (`VinAI/PhoWhisper-large`) | **BSD-3** (code + weights, không gated) | 🟢 Nên thử A/B | Fine-tune Whisper trên 844h tiếng Việt — **weights permissive duy nhất** tìm được cho VI |
| Chuẩn hoá timestamp / cắt cue | **stable-ts** `jianfch/stable-ts` | **MIT** | 🟢 **ADOPT — chất lượng SRT** | `regroup` (gộp theo dấu câu + khoảng lặng), `suppress_silence`, `gap_adjust` — trực tiếp cải thiện SRT ta đang tự viết tay |
| VAD (chunking) | **Silero VAD** `snakers4/silero-vad` | **MIT** | 🟢 ADOPT | Chuẩn de-facto, ONNX 1–2MB, chạy realtime CPU |
| Diarization (đang dùng) | **pyannote-audio** `pyannote/pyannote-audio` | code **MIT**; weights: `speaker-diarization-3.1` MIT (gated), `community-1` **CC-BY-4.0** (gated) | ✅ Đang dùng | **Nâng cấp ứng viên:** `community-1` mới hơn, đếm/gán speaker tốt hơn 3.1 — ta đang gọi 3.1 trong `stt.py` |
| Diarization không bị gated | **WeSpeaker** `wenet-e2e/wespeaker`, **3D-Speaker** `modelscope/3D-Speaker` (CAM++) | **Apache-2.0** | 🟡 Phương án B | Tự sở hữu stack (embedding + clustering) → bỏ hẳn phụ thuộc HF gated |
| Diarization streaming | **diart** `juanmc2005/diart` | **MIT** | 🟡 Tham khảo | Kiến trúc buffer/queue online (cho live dub) |
| Alignment từng từ | **WhisperX** `m-bain/whisperX` | **BSD-2** | 🟢 ADOPT thuật toán | `get_trellis`/`backtrack`/`interpolate_nans` + `merge_chunks` VAD |
| Serialize phụ đề SRT/VTT/**ASS** | **pysubs2** `tkarabela/pysubs2` | **MIT** | 🟢 **ADOPT — thay `to_srt()` tự viết** | Hỗ trợ style ASS, phụ đề song ngữ, chuyển format lossless |
| Parse SRT + tách dòng song ngữ | **cdown/srt** | **MIT** | 🟢 ADOPT (nhỏ) | ~200 dòng, ổn định |
| Render ASS trong browser | **JASSUB** (libass WASM) | **MIT** (libass **ISC**) | 🟢 ADOPT khi cần preview | Khớp với ffmpeg burn-in |
| Quy tắc CPS/độ dài dòng | **SubtitleEdit** (C#) — dùng như **spec**, không port code | **MIT** (bản hiện tại; bản cũ **GPL-3.0**) | 🟡 Học spec | CPS ~20, min/max duration, auto-bridge gaps, dual-subtitle |
| AWS burn phụ đề | **FFmpeg** `ass`/`subtitles` filter | LGPL-2.1 **hoặc GPL-2.0 nếu build `--enable-gpl`** | ⚠️ Chạy như CLI riêng | Tránh build GPL (libx264...) nếu muốn an toàn |

### 1.4 "Tạo video bằng AI" (mockup có trong sidebar)

| Model | License code / **weights** | VRAM | Hành động |
|---|---|---|---|
| **Wan2.1-T2V-1.3B** `Wan-Video/Wan2.1` | Apache-2.0 / **Apache-2.0** | ~8.2 GB | 🟢 **ADOPT** — sạch cả code lẫn weights |
| **Wan2.2-TI2V-5B** | Apache-2.0 / **Apache-2.0** | 1×4090 (720p) | 🟢 **ADOPT** — chất lượng/GPU tiêu dùng tốt nhất |
| **CogVideoX-2B** `zai-org/CogVideo` | Apache-2.0 / **Apache-2.0** | 3.6 GB INT8 | 🟢 ADOPT (nhẹ nhất) |
| CogVideoX-5B | Apache-2.0 / license riêng (`other`) | 14–18 GB | 🟡 Đọc điều kiện |
| LTX-Video, HunyuanVideo, SVD | Apache-2.0 / **license riêng** (giới hạn doanh thu, loại trừ EU/UK/KR…) | — | 🔴 Tránh nếu chưa đọc kỹ |
| Mochi 1, Open-Sora | Apache-2.0 / Apache-2.0 | 42 GB / cao | 🟡 Nặng |

### 1.5 UI/UX + hạ tầng platform

| Thành phần (mockup) | Dự án | License | Hành động |
|---|---|---|---|
| **Waveform đa track** (Nhân vật 1/2 + Nhạc nền) | **wavesurfer.js** `katspaugh/wavesurfer.js` (+ plugin multitrack), hoặc **waveform-playlist** `naomiaro/waveform-playlist` | **BSD-3** / **MIT** | 🟢 ADOPT cho UI chính |
| Editor audio zero-build (vanilla JS) | **AudioMass** `pkalogiros/AudioMass` | **MIT** | 🟢 Học UX (khớp ràng buộc "không build step" của ta) |
| Điều khiển media không cần build | **media-chrome** `muxinc/media-chrome` | **MIT** | 🟢 ADOPT (Web Components) |
| Lên lịch phát đa track chính xác | **Tone.js** `Tonejs/Tone.js` | **MIT** | 🟡 ADOPT khi cần |
| Biểu đồ usage theo tháng | **Chart.js** (**MIT**) / **Apache ECharts** (**Apache-2.0**) | — | 🟢 ADOPT (vanilla JS, zero-build) |
| i18n 100+ ngôn ngữ | **i18next** `i18next/i18next` | **MIT** | 🟢 ADOPT (core chạy vanilla JS) |
| Upload lớn, resume được | **tus-js-client** (MIT) + **tusd** (MIT) | MIT | 🟡 ADOPT khi media lớn |
| Webhook signing chuẩn hoá | **Standard Webhooks** spec | **Apache-2.0** | 🟢 ADOPT — ta đã có HMAC; chuẩn hoá header/timestamp để tương thích |
| Hàng đợi job + progress | Ta dùng **Celery** (BSD-3) ✅; thay thế nhẹ hơn: **arq**/**taskiq**/**SAQ** (đều MIT) | BSD/MIT | 🟡 Cân nhắc; SAQ có sẵn progress/status |
| Metering/credits | **OpenMeter** `openmeterio/openmeter` | **Apache-2.0** | 🟡 Học mô hình event→aggregate |
| Phân quyền/entitlements | **OpenFGA**, **Cerbos**, **Casbin** | **Apache-2.0** | 🟡 Khi có gói trả phí |
| UI quản lý API key | **Unkey** — **chỉ học thiết kế** (prefix, scope, last-used, revoke) | code **AGPL-3.0** | 🔴 **KHÔNG copy code** |

### 1.6 Hạ tầng lưu trữ — ⚠️ CỜ ĐỎ cần quyết định

| Thành phần | License (đã fetch LICENSE) | Ghi chú |
|---|---|---|
| **MinIO** (compose hiện tại của ta) | **AGPL-3.0** | Dùng *nguyên bản, không sửa* làm service backend là thực tế phổ biến và **không** làm dính AGPL lên code của ta — nhưng nếu muốn stack **zero-copyleft** thì đây là mắt xích duy nhất không permissive |
| **Garage** `deuxfleurs/garage` | **AGPL-3.0** | Cùng vấn đề |
| **SeaweedFS** `seaweedfs/seaweedfs` | **Apache-2.0** | ✅ Thay thế sạch (S3-compatible) |
| AWS S3 / Cloudflare R2 | dịch vụ | ✅ Không vấn đề license; `S3Storage` của ta đã hỗ trợ |

> Ta đã tách lớp storage (`S3Storage` ↔ `LocalStorage` qua `S3_ENDPOINT`) nên **đổi
> backend chỉ là đổi service trong compose**, không sửa code pipeline.

## 1b. Bốn repo được chủ dự án chỉ định — kết quả xác minh (27/09/2026)

Đã fetch file `LICENSE` thật của từng repo. **Chỉ 2 trong 4 được copy code.**

| Repo | License (verify từ file thật) | OSI? | Copy code vào Apache-2.0? |
|---|---|---|---|
| **open-webui** ≥ v0.6.6 (nhánh `main` hiện tại) | "Open WebUI License" = BSD-3 **+ điều khoản 4 bắt giữ branding** | ❌ Không | 🔴 **KHÔNG** |
| **open-webui** ≤ **v0.6.5** | **BSD-3-Clause** (thuần) | ✅ | 🟢 **ĐƯỢC** — pin đúng tag |
| **omlx** `jundot/omlx` | **Apache-2.0** | ✅ | 🟢 **ĐƯỢC** |
| **VoiceStudio** `debpalash/VoiceStudio` | **AGPL-3.0-only** + weights **CC-BY-NC** | ✅ (code) | 🔴 **KHÔNG** |
| **ArcReel** `ArcReel/ArcReel` | **AGPL-3.0** + điều khoản §7 buộc ghi công | ✅ (code) | 🔴 **KHÔNG** |

Chi tiết quan trọng:

- **open-webui — mốc đổi license đã xác định chính xác:** commit `60d84a3` ("chore: license
  'branding' clause", 18/04/2025). Kiểm tra bằng cách grep `LICENSE` tại từng tag:
  **v0.6.5 = BSD-3** (bản cuối cùng còn permissive), **v0.6.6 trở đi = license riêng**.
  Điều khoản 4 nói lệnh cấm chỉ áp dụng **khi vượt 50 người dùng trong 30 ngày** — nhưng vì
  đây là "material condition of the rights granted", **không thể** mang code đó vào sản phẩm
  Apache-2.0 (Apache-2.0 không cho phép áp thêm hạn chế xuống người nhận sau).
  → Muốn copy: `git checkout v0.6.5` rồi lấy từ đó, giữ nguyên copyright.
- **omlx — nguồn copy tốt nhất trong 4 repo:** `omlx/api/adapters/{openai,anthropic,base}.py`
  + `sse_formatter.py` + `parser_tool_calls.py` + các schema model (`openai_models.py`,
  `embedding_models.py`, `audio_models.py`) là code độc lập, không phụ thuộc SwiftUI. Phần
  app macOS (SwiftUI/Metal) chỉ để tham khảo.
- **VoiceStudio:** code AGPL (lây nhiễm toàn bộ dịch vụ) **và** weights mặc định
  (`k2-fsa/OmniVoice`) là **CC-BY-NC** — không dùng thương mại được. Đọc `LICENSE-NOTICE.md`
  của họ có ghi rõ. Chỉ nên đọc `backend/services/llm_providers.py` +
  `backend/config/models.yaml` để **học cách mô tả catalog provider**, và
  `docs/electron-llm-providers.md` để học quy tắc "test trước khi kích hoạt, giữ nguyên key
  khi ô để trống" — đúng những quy tắc ta áp dụng ở mục 3.2 của kế hoạch.
- **ArcReel:** AGPL + NOTICE §7(b) buộc mọi bản sửa phải giữ dòng "Powered by ArcReel" và
  **link tới repo gốc ở vị trí hiển thị** — không phù hợp white-label/self-host thương mại.
  Frontend của họ (React, không phải Svelte) có cụm `settings/endpoints/*` và
  `PromptTemplate*` rất đáng **học bố cục**, nhưng không copy.

## 2. Danh sách "KHÔNG dùng" (đã xác minh lý do)

| Dự án | Vấn đề |
|---|---|
| **Wav2Lip** & các fork (Wav2Lip-HD, GFPGAN…) | **Không có license + README cấm thương mại** rõ ràng |
| **fish-speech** | Đổi sang "Fish Audio Research License" — **cấm thương mại** (nhiều người tưởng Apache) |
| **Whisper weights XTTS-v2** (`coqui/XTTS-v2`) | Code MPL-2.0 nhưng **weights CPML non-commercial** |
| **F5-TTS base weights**, **Spark-TTS weights** | CC-BY-NC-4.0 |
| **IndexTTS-2** | License riêng của bilibili, không OSI |
| **MARS5-TTS, ChatTTS, so-vits-svc, whisper-timestamped, aeneas** | **AGPL-3.0** → lây nhiễm toàn bộ dịch vụ |
| **pyvideotrans, voice-pro, seed-vc, Auto-Synced-Translated-Dubs** | **GPL-3.0** |
| **Lago, Unkey, Documenso, Plane, Dub, cal.com (lịch sử)** | **AGPL-3.0** — chỉ học UI/UX |
| **Hook0** (webhook) | **SSPL-1.0** |
| **ComfyUI** | **GPL-3.0** — không nhúng; nếu dùng phải gọi out-of-process |
| **MMS-based aligners** (`torchaudio MMS_FA`, ctc-forced-aligner), **Sortformer**, **Canary-v1**, **Moonshine VI legacy** | **Weights CC-BY-NC-4.0** |
| **`nguyenvulebinh/wav2vec2-*-vietnamese`** | **CC-BY-NC-4.0** — hay bị chọn nhầm làm aligner tiếng Việt |
| **VieNeu v4** | Proprietary (chỉ API, không OSS) — ta dùng **v3 Turbo** |

## 3. Khoảng trống chưa có giải pháp permissive

1. **Aligner tiếng Việt** (buộc-thời-gian từng từ): **không có** model wav2vec2 tiếng Việt
   nào permissive. Mọi bản sẵn có đều CC-BY-NC. Hướng đi hợp lệ:
   - (a) train/fine-tune CTC tiếng Việt trên base **`facebook/wav2vec2-xls-r-300m` (Apache-2.0)**
     rồi chạy code alignment của WhisperX (BSD-2), hoặc
   - (b) dùng `torchaudio.functional.forced_align` (BSD-2) với model CTC tự có, hoặc
   - (c) dùng **MFA** (code MIT) sau khi verify license model `vietnamese_mfa`.
2. **Giữ nhạc nền tử tế** — giải quyết được bằng Demucs (MIT), chỉ chưa triển khai.
3. **TTS đa ngôn ngữ có tiếng Việt trong cùng một model** — chưa tồn tại bản permissive;
   hiện phải ghép VieNeu (vi) + engine khác (non-vi) sau provider layer.

## 4. Lộ trình áp dụng vào repo này (theo thứ tự ưu tiên)

| # | Việc | Nguồn tham chiếu | Điểm chạm trong code | Chi phí |
|---|---|---|---|---|
| 1 | Bộ chống hallucination cho Whisper | faster-whisper (MIT) | `app/pipelines/stt.py::transcribe` | ~5 dòng |
| 2 | SRT/VTT/ASS + phụ đề song ngữ | pysubs2 (MIT) | thay `app/pipelines/stt.py::to_srt` | nhỏ |
| 3 | Chuẩn hoá cue (gộp theo dấu câu/khoảng lặng) | stable-ts (MIT) | `stt.py::merge` + segment hậu kỳ | vừa |
| 4 | **Track nhạc nền thật** (tách stem) | Demucs (MIT) | `app/pipelines/dub_pipeline.py::_make_bed` | vừa (thêm dep) |
| 5 | Vòng lặp re-translate cho `needs_shorter_text` | VideoLingo (Apache-2.0) | `dub.py` + `dub_pipeline.py` | vừa |
| 6 | Retime phụ đề lên audio đã dub | ffsubsync (MIT) | stage mới sau mix | nhỏ |
| 7 | Waveform đa track cho UI chính | wavesurfer.js (BSD-3) | `backend/app/app_ui.py` | vừa |
| 8 | Nâng pyannote `3.1` → `community-1` | pyannote (CC-BY-4.0 weights) | `stt.py::DIA_MODEL` | nhỏ (cần accept repo) |

**Khi copy code permissive:** giữ nguyên header copyright của tác giả gốc, ghi nguồn
trong file (hoặc `NOTICE`), và nêu rõ license — MIT/Apache/BSD đều yêu cầu điều này.