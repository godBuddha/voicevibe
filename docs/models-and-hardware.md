# Chọn model: chạy trên máy (local) hay trên mây (cloud)?

Tài liệu này trả lời 3 câu hỏi của người self-host:

1. **Chức năng nào nên dùng model chạy trên máy mình, chức năng nào nên thuê trên mây?**
2. **Có những nhà cung cấp (provider) nào cho từng chức năng?**
3. **Mua/thuê GPU cỡ nào là đủ?** (bắt đầu từ dòng RTX 2000)

> Liên quan: giấy phép mã nguồn + trọng số từng model — xem `docs/oss-references.md`.

---

## 1. Nguyên tắc chọn (3 câu, không thuật ngữ)

- **Phần dịch văn bản → mây.** Máy dịch cỡ DeepSeek/Qwen trên mây dịch chuẩn hơn
  rất nhiều so với bộ dịch nhỏ chạy máy bạn, mà giá chỉ khoảng vài nghìn đồng
  cho cả cuốn phim. Không có lý do nào phải tự dịch.
- **Phần "biết giọng ai" và "học giọng của bạn" → bắt buộc chạy máy mình.**
  Chuẩn API mây phổ biến (chuẩn OpenAI) chỉ bán **giọng có sẵn** của hãng và trả
  về **chữ trơn** — không có khái niệm "câu này do người A nói" hay "học từ
  file giọng mẫu của bạn". Ba khâu này không thuê được, chỉ chạy tại chỗ.
- **Phần còn lại (nghe thành chữ, đọc thành tiếng) → hai bên đều được.**
  Chọn theo tiền và thời gian: dùng thi thoảng/video ngắn → mây rẻ hơn việc
  sở hữu GPU; dùng thường xuyên/video dài → máy mình rẻ về lâu dài.

Ví dụ dễ hiểu: lồng tiếng 1 video 10 phút = 5 khâu nối tiếp —

```
nghe ra chữ → dịch → học/đọc lại giọng → biết ai nói lúc nào → trộn nhạc nền
   [2 bên]      [mây]        [2 bên]            [chỉ máy mình]    [chỉ máy mình]
```

Vì "biết ai nói" và "trộn nhạc nền" bắt buộc chạy máy mình, **một video lồng
tiếng luôn cần GPU local**, dù dịch và nghe-ra-chữ có thuê mây đi nữa.

---

## 2. Bảng quyết định nhanh

| # | Chức năng (trang trong app) | Máy mình (local) | Mây (cloud) | Khuyến nghị |
|---|---|---|---|---|
| 1 | Dịch văn bản (lồng tiếng, phụ đề song ngữ) | opus-mt nhỏ (chạy CPU được) | DeepSeek / Qwen / Gemini qua OpenRouter | **Mây** — chất lượng hơn hẳn, giá lẻ tẻ |
| 2 | Nghe ra chữ — STT | Whisper (faster-whisper large-v3) | whisper-large-v3, turbo (mây tính theo giây) | **Máy mình** cho phụ đề + lồng tiếng (cần mốc thời gian từng câu); mây chỉ dùng để "lấy chữ nhanh" |
| 3 | Đọc thành tiếng — TTS | VieNeu v3 Turbo (giọng Việt + clone) | giọng có sẵn (MiniMax 2.8, OpenAI tts) | **Máy mình** — vì clone + tự nhiên tiếng Việt; mây là phương án dự phòng giọng có sẵn |
| 4 | Nhân bản giọng của bạn (trang Giọng Clone) | VieNeu v3 (nạp file mẫu 10–20 giây) | ❌ không có chuẩn mây nào nhận file mẫu | **Bắt buộc máy mình** |
| 5 | Phân biệt ai nói câu nào (diarization) | pyannote 3.1 | ❌ không có | **Bắt buộc máy mình** |
| 6 | Tách nhạc nền khỏi giọng (Demucs) | Demucs htdemucs | ❌ không có | **Bắt buộc máy mình** |
| 7 | Canh thời gian từng câu khớp với giọng mới (timing-fit) | stable-ts + phép canh trên máy | ❌ không có | **Bắt buộc máy mình** |

> Kết luận rút gọn: **mây cho mục 1 (và tùy chọn mục 2/3), GPU local là xương
> sống của 4/7 khâu.** Xóa máy GPU chỉ làm chậm đi, không làm chết chức năng nào.

---

## 3. Vì sao 4 khâu không thuê mây được

Lý do nằm ở **chuẩn API chung** mà các nhà mây đều theo (chuẩn của OpenAI):

- Endpoint **đọc thành tiếng** (`POST /v1/audio/speech`) nhận `text + voice`,
  trong đó `voice` là **tên giọng có sẵn của hãng** (ví dụ `alloy`, hay mã giọng
  MiniMax). Chuẩn này **không có chỗ để nộp file giọng mẫu** — nên "học giọng
  từ file của bạn" không thể đi qua mây. Một số hãng có tiện ích clone riêng
  (thuộc dịch vụ riêng của họ, khóa vào tài khoản hãng, không nằm trong chuẩn).
- Endpoint **nghe ra chữ** (`POST /v1/audio/transcriptions`) trả về các đoạn
  `bắt đầu – kết thúc – chữ`, **không trả nhãn người nói**. Phân biệt "người A /
  người B" là một khâu máy học khác (pyannote) chạy ngay trên audio — mây phổ
  thông không bán khâu này.

Vì vậy trong code, lớp provider (`backend/app/providers/`) ghi rõ ràng điều
này — `openai_compat.py` docstring: *"cloning stays local … diarization stays
local (pyannote)"*. Hệ thống hiện có 3 loại mây (`openai_chat`,
`openai_tts`, `openai_stt`) và 2 loại máy (`local_vieneu`, `local_whisper`).

---

## 4. Rà soát nhà cung cấp cho từng chức năng

### 4.1 Dịch văn bản (khâu 1)

| Nơi cung cấp | Loại | Ghi chú |
|---|---|---|
| **OpenRouter** → DeepSeek / Qwen / Gemini / GPT | `openai_chat` | 1 chìa khóa dùng được nhiều hãng, tự chuyển hướng khi hãng nào quá tải — khuyến nghị mặc định |
| **DeepSeek** trực tiếp | `openai_chat` | Rẻ nhất cho tiếng Việt ↔ tiếng Trung/Anh |
| **Google / OpenAI** trực tiếp | `openai_chat` | Dự phòng khi OpenRouter lỗi |
| **Ollama / vLLM** chạy máy mình (Qwen3) | `openai_chat` (cùng chuẩn!) | Cách mạng không cần internet; card 8 GB chạy nổi Qwen3-4B |
| **opus-mt (Marian)** gắn sẵn | builtin | Bộ dịch nhỏ ~300 MB, chất lượng "tạm được" — là **bước dự phòng cuối** khi mọi provider hỏng |

Giá tham khảo (09/2026): dịch toàn bộ lời thoại của một video 10 phút tốn
**dưới 1 cent** với DeepSeek/Qwen — gần như miễn phí so với tiền GPU.

### 4.2 Nghe ra chữ — STT (khâu 2)

| Nơi cung cấp | Chuẩn | Giá tham khảo (09/2026) |
|---|---|---|
| **Máy mình: faster-whisper large-v3** | builtin `local_whisper` | Miễn phí; card 8 GB chạy được (chế độ nén int8 ~2,5–3 GB), 12 GB chạy nguyên bản fp16 (~4–5 GB) |
| **OpenAI trực tiếp** (whisper-1, gpt-4o-transcribe) | `openai_stt` (multipart chuẩn) | ~$0,006/phút |
| **Groq / DeepInfra** | `openai_stt` | Nhận multipart chuẩn OpenAI, nhanh nhất thị trường |
| **OpenRouter** (whisper-large-v3) | KHÔNG giống multipart | $0,000008/giây (≈ $0,48/giờ); bản turbo $0,000003/giây. **Lưu ý:** OpenRouter yêu cầu nộp audio dạng **base64 trong JSON**, khác với chuẩn multipart — cần bộ nối riêng nếu muốn dùng |

**Lưu ý quyết định:** mây trả *đoạn chữ có mốc giờ*, nhưng phụ đề và lồng tiếng
cần **mốc giờ chuẩn từng câu khớp với file mới tạo** — bước canh thời gian của
hệ thống làm trên máy local với chính audio nó tạo ra. Dùng STT mây đồng nghĩa
với phụ đề lệch thời gian. Cho nên:

- Job **phụ đề / lồng tiếng** → luôn `local_whisper`.
- Job **lấy chữ nhanh** (không cần mốc giờ chuẩn) → mây tiết kiệm GPU tốt.

### 4.3 Đọc thành tiếng — TTS (khâu 3)

| Nơi cung cấp | Chuẩn | Giá tham khảo (09/2026) |
|---|---|---|
| **Máy mình: VieNeu-TTS v3 Turbo** | builtin `local_vieneu` | Miễn phí; có GPU RTF ~0,02 (đọc 10 phút mất ~12 giây); không GPU chạy chế độ ONNX CPU (đọc 10 phút mất ~5 phút) |
| **OpenAI trực tiếp** (tts-1, gpt-4o-mini-tts) | `openai_tts` | ~$15/triệu ký tự — giọng tiếng Anh rất tự nhiên, tiếng Việt phụ thuộc model |
| **OpenRouter** (MiniMax speech-2.8-hd/turbo, Google, Mistral) | `openai_tts` (cùng chuẩn) | MiniMax HD $100/triệu ký tự ≈ **$0,8 cho ~8.000 ký tự** (khoảng 10 phút lời thoại) — nhiều giọng tiếng Việt tốt |
| **ElevenLabs** và các dịch vụ riêng khác | không cùng chuẩn | Cần viết bộ nối riêng; ngoài phạm vi hiện tại |

Điều kiện dùng mây: **bạn phải chấp nhận giọng có sẵn của hãng**. Giọng bạn đã
nhân bản thì chỉ máy local hiểu được (khâu 4).

### 4.4–4.7 Khâu chỉ chạy máy mình

| Khâu | Engine gắn sẵn | Giấy phép | RAM/VRAM |
|---|---|---|---|
| Nhân bản giọng | VieNeu v3 Turbo (instant clone) | Apache-2.0 | cùng GPU với TTS |
| Phân biệt người nói | pyannote.audio 3.1 | code MIT, trọng số MIT (cần bấm "đồng ý" trên HuggingFace) | ~2–3 GB |
| Tách nhạc nền | Demucs htdemucs | MIT | ~2–3 GB |
| Canh thời gian | stable-ts + pysubs2 | BSD-2 / MIT | CPU |

> **Cảnh báo giấy phép** (chi tiết ở `docs/oss-references.md`): các model đang
> hot như F5-TTS, XTTS-v2, Spark-TTS và các bộ nhận dạng tiếng Việt dựa trên
> wav2vec2 đều có trọng số **"không cho dùng thương mại" (CC-BY-NC)** — dù mã
> nguồn của chúng thoải mái. Đừng cài vào vì "chất lượng hơn một chút" rồi
> chết giấy phép.

---

## 5. Gắn provider vào hệ thống như thế nào

Mọi thứ ở trên đã có sẵn chỗ cắm — không phải sửa code, chỉ cấu hình trong
**Trang quản trị → AI (Model Hub)**:

1. Thêm **provider**: dán Base URL + API key (ví dụ OpenRouter
   `https://openrouter.ai/api/v1`, hay Ollama nội bộ `http://ollama:11434/v1`).
2. Gán **công đoạn** cho provider đó. Hệ thống có 5 công đoạn cắm được:
   `stt`, `translate`, `retranslate`, `tts`, `dub` — mỗi công đoạn được xếp
   **chuỗi dự phòng** (thử cái đầu, hỏng thì tự nhảy xuống cái sau).
3. Không cấu hình gì? Mọi công đoạn tự dùng engine local mặc định trong
   `worker`.

Ví dụ 2 chuỗi thực tế đã chạy tốt (cấu hình qua Model Hub hoặc
`translate.*` trong Cấu hình hệ thống):

```
dịch:      OpenRouter/DeepSeek  →  Ollama nội bộ (Qwen3-4B)  →  opus-mt builtin
tts:       VieNeu máy mình      →  giọng có sẵn trên mây (preset)
```

Cách hiểu chuỗi: **để dịch và TTS, hệ thống luôn có chuyện làm** — mây chết thì
nhảy về máy mình, máy mình thiếu GPU thì nhảy về ONNX CPU. Không có trạng thái
"chết hẳn".

---

## 6. Phần cứng GPU: mua/cường nào là đủ (từ RTX 2000)

### 6.1 Mỗi khâu cần bao nhiêu bộ nhớ hiển thị (VRAM)

Bảng ước lượng từ cấu hình thật trong `backend/requirements-worker.txt`:

| Khâu | VRAM |
|---|---|
| STT Whisper small | ~1 GB |
| STT Whisper medium | ~2,5 GB |
| **STT Whisper large-v3 (fp16)** — chất lượng cao nhất | **~4–5 GB** ← khâu "ăn VRAM nhất" |
| STT Whisper large-v3 (nén int8) | ~2,5–3 GB |
| Phân biệt người nói (pyannote) | ~2–3 GB |
| Tách nhạc nền (Demucs) | ~2–3 GB |
| TTS VieNeu v3 Turbo | ~3–4 GB |

**Điểm mấu chốt:** worker chạy **tuần tự** (một lúc một khâu), nên card chỉ cần
đủ cho **khâu lớn nhất**, không phải cộng hết. Nghĩa là:

- **6 GB** — đủ, nhưng phải dùng Whisper nén int8, hơi gò bó.
- **8 GB** — ngưỡng thoải mái tối thiểu (int8 lớn nhất hoặc fp16 vừa đủ).
- **12 GB** — dư dả, chạy nguyên bản fp16 + còn thừa cho việc khác.
- **16 GB+ / 24 GB** — chỉ cần khi video dài, chạy nhiều job song song, hoặc
  muốn mở rộng sau này (model video AI…).

### 6.2 Bảng đề xuất theo túi tiền

| Ngân sách | Card đề xuất | VRAM | Nhận xét |
|---|---|---|---|
| Mới chơi / máy cũ | **RTX 2060 Super** (máy đã dùng) | 8 GB | Lối vào rẻ nhất vẫn đủ chạy full pipeline (Whisper int8) |
| Máy đã dùng giá rẻ | **RTX 2080 Ti** | 11 GB | "Kép VRAM" tốt nhất hàng cũ; chấp nhận nguồn 250W + không bảo hành |
| **Mua mới — ngọt nhất** | **RTX 3060 12 GB** | 12 GB | **Khuyến nghị chính**. Đã verify trong repo (driver 550). Nhỏ, mát (170W), VRAM 12 GB |
| Làm nghiêm túc | **RTX 3090 / 3090 Ti** (máy đã dùng) | 24 GB | Hộp GPU 2×3090 đã chạy end-to-end đủ 5 luồng của hệ thống |
| Mua mới thế hệ 40 | **RTX 4060 Ti 16 GB** | 16 GB | Nhảy cóc lên 16 GB, điện chỉ 165W. **Tránh bản 8 GB** |
| Mua mới thế hệ 40/50 | RTX 4070 Ti Super / 5070 Ti | 16 GB | 16 GB + tốc độ cao, nếu giá hợp lý |
| Dư dả / mở rộng | RTX 4090 / 5090 | 24 / 32 GB | Hơn nhu cầu của hệ thống hiện tại — chỉ mua khi chạy nhiều job song song hoặc định mở rộng sang model video AI |

**Tránh:** RTX 3050/4060 8 GB (chạy được nhưng VRAM là bức tường); card NVIDIA
trước 2000 series (GTX 10xx trở xuống) — wheel torch 2.8 (cu128) ghim trong repo
**hỗ trợ từ kiến trúc Turing (RTX 20) trở lên**.

**Laptop:** dòng 2060/3060/4070 laptop đều chạy được, nhưng nhiệt độ máy laptop
khiến tốc độ tụt 20–40% khi xử lý dài — chỉ dùng khi không có lựa chọn.

### 6.3 Không có GPU thì sao?

**Vẫn chạy được đủ 5 luồng** — hệ thống sinh ra theo kiểu "thoát được khi không
có GPU":

- Whisper chạy chế độ nén int8 trên CPU (1 phút audio ≈ 1–2 phút chờ);
- VieNeu chạy chế độ ONNX CPU (RTF ~0,5 — đọc 10 phút mất ~5 phút);
- Demucs chạy CPU (chậm hơn GPU khoảng 5–10 lần).

Phù hợp demo, video ngắn, test chức năng. Video dài thì... pha cà phê đợi.

### 6.4 Chi phí so sánh — ví dụ một video 10 phút lời thoại (Anh → Việt)

| Phương án | Tiền | Thời gian chờ |
|---|---|---|
| Toàn bộ chạy máy mình (3060 12 GB) | tiền điện ~2–4k VND | lồng tiếng ~15–30 phút |
| STT mây + dịch mây + TTS mây, 4 khâu chỉ-máy-mình chạy GPU local | STT ≈ $0,005 + dịch < $0,01 + TTS MiniMax ≈ $0,8 → **≈ $0,8–1** (~25k VND) | nhanh hơn local ở khâu TTS |
| Toàn bộ mây | không khả thi — 4 khâu không có mây | — |

**Kết luận:** dùng thi thoảng (vài video/tuần) → giữ GPU local cỡ 3060 12 GB là
cân nhất; thuê mây chỉ hợp khi bạn chưa có GPU nào và chỉ xử lý video ngắn.

---

## 7. Tóm lại — 3 cấu hình khuyến nghị

| Kịch bản | Cấu hình |
|---|---|
| **Thử nghiệm / demo** | Không GPU, mọi khâu local CPU + dịch qua OpenRouter. Chi phí: ~0 |
| **Self-host cá nhân** | GPU 8–12 GB (2060 Super / 3060 12 GB) + OpenRouter cho dịch. Chi phí: một lần mua card + vài nghìn đồng/tháng dịch |
| **Dịch vụ cho nhiều người** | GPU 24 GB (3090 / 4090) chạy worker + OpenRouter. Scale worker bằng cách tăng số job chạy song song |
