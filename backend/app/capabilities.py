"""Capability Registry — nguồn sự thật DUY NHẤT về capability model và chức năng hệ thống.

Vì sao cần: cũ từng "đánh giá" model bằng cách đoán theo tên (gpt → chat, whisper → STT).
Yêu cầu thiết kế: KHÔNG được suy đoán từ tên; chỉ dùng metadata chính thức của provider,
thiếu metadata thì model dừng ở "unknown". Registry này là nơi DUY NHẤT khai báo:

- `CAPABILITIES`     — 18 cờ capability model (True/False/None).
- `SYSTEM_FEATURES`  — 16 chức năng của VoiceVibe, mỗi chức năng khai báo capability
                       BẮT BUỘC / TUỲ CHỌN. Compatibility engine (compat.py) đối chiếu
                       capabilities của model với registry này — không hard-code ở đâu khác.
- `STAGE_FEATURES`   — map công đoạn pipeline (stt/translate/...) → feature key, để
                       model selector của từng công đoạn biết lọc model nào.

LƯU Ý THIẾT KẾ: các feature *dịch thuật* đặt `translation` là capability TUỲ CHỌN
(required = [text, chat]). Không nhà cung cấp nào khai báo "translation" trong metadata
chính thức — nếu bắt buộc thì mọi model mãi mãi dừng ở "một phần" và selector của stage
translate (công đoạn quan trọng nhất) luôn rỗng. CloudChatTranslator dịch bằng prompt
trên model chat, nên [text, chat] là điều kiện ĐỦ về mặt kỹ thuật; `translation` chỉ là
booster điểm. Muốn siết lại: sửa `required` ở đây — mọi thứ khác không đổi.

`local_engine: True` đánh dấu feature chạy engine cục bộ (VieNeu TTS clone...) —
không model cloud nào qua registry được dùng cho nó; compatibility engine bỏ qua.
"""
from __future__ import annotations

# ---- 18 capability của model. Giá trị: True / False / None (chưa xác định).
# None là trạng thái HỢP LỆ và quan trọng: "provider không khai báo" khác
# "provider khai báo không có" — gộp hai cái thành một là tự suy đoán.
CAPABILITIES: tuple[str, ...] = (
    "text", "chat", "reasoning", "vision",
    "imageGeneration", "imageUnderstanding",
    "audioInput", "audioOutput",
    "speechToText", "textToSpeech", "translation",
    "videoInput", "videoGeneration",
    "embeddings", "reranking",
    "functionCalling", "structuredOutput", "streaming",
)

CAPABILITY_LABELS: dict[str, str] = {
    "text": "Văn bản",
    "chat": "Chat",
    "reasoning": "Suy luận",
    "vision": "Thị giác",
    "imageGeneration": "Sinh ảnh",
    "imageUnderstanding": "Hiểu ảnh",
    "audioInput": "Nhận audio",
    "audioOutput": "Xuất audio",
    "speechToText": "Giọng nói → văn bản",
    "textToSpeech": "Văn bản → giọng nói",
    "translation": "Dịch thuật",
    "videoInput": "Nhận video",
    "videoGeneration": "Sinh video",
    "embeddings": "Vector nhúng",
    "reranking": "Xếp hạng lại",
    "functionCalling": "Gọi hàm",
    "structuredOutput": "Kết quả có cấu trúc",
    "streaming": "Streaming",
}

# ---- 16 chức năng hệ thống. THỨ TỰ khai báo = thứ tự trả ra API/UI.
# `required`  — thiếu bất kỳ capability nào đã biết là False ⇒ model KHÔNG làm được.
# `optional`  — có thì điểm cao hơn, không có vẫn đủ điều kiện.
#             CẨN THẬN: chỉ đưa vào optional những capability có nhiều khả năng None
#             (không nhà cung cấp nào khai báo) — đưa capability có nguồn False
#             vào optional sẽ khiến model bị trừ điểm vô cớ.
SYSTEM_FEATURES: dict[str, dict] = {
    "text_generation": {
        "label": "Sinh văn bản / Chat",
        "required": ["text", "chat"],
        "optional": ["functionCalling", "structuredOutput", "reasoning", "streaming"],
    },
    "text_translation": {
        "label": "Dịch văn bản",
        "required": ["text", "chat"],
        "optional": ["translation", "structuredOutput"],
    },
    "subtitle_translation": {
        "label": "Dịch phụ đề",
        "required": ["text", "chat"],
        "optional": ["translation"],
    },
    "audio_translation": {
        "label": "Dịch âm thanh",
        "required": ["audioInput", "text"],
        "optional": ["translation"],
    },
    "video_translation": {
        "label": "Lồng tiếng video",
        "required": ["audioInput", "text"],
        "optional": ["translation"],
    },
    "speech_to_text": {
        "label": "Giọng nói → văn bản",
        "required": ["speechToText"],
        "optional": [],
    },
    "text_to_speech": {
        "label": "Văn bản → giọng nói",
        "required": ["textToSpeech"],
        "optional": [],
    },
    "voice_cloning": {
        "label": "Nhân bản giọng nói",
        "required": [], "optional": [], "local_engine": True,
    },
    "voice_conversion": {
        "label": "Chuyển đổi giọng nói",
        "required": [], "optional": [], "local_engine": True,
    },
    "image_understanding": {
        "label": "Hiểu ảnh",
        "required": ["imageUnderstanding"],
        "optional": [],
    },
    "image_generation": {
        "label": "Sinh ảnh",
        "required": ["imageGeneration"],
        "optional": [],
    },
    "video_understanding": {
        "label": "Hiểu video",
        "required": ["videoInput"],
        "optional": [],
    },
    "video_generation": {
        "label": "Sinh video",
        "required": ["videoGeneration"],
        "optional": [],
    },
    "reasoning": {
        "label": "Suy luận",
        "required": ["reasoning"],
        "optional": [],
    },
    "embedding": {
        "label": "Vector nhúng",
        "required": ["embeddings"],
        "optional": [],
    },
    "reranking": {
        "label": "Xếp hạng lại",
        "required": ["reranking"],
        "optional": [],
    },
}

# Công đoạn pipeline → feature tương ứng (dùng cho model selector của stage).
# "subtitle" ở đây là công đoạn dịch phụ đề trong pipeline subtitle.
STAGE_FEATURES: dict[str, str] = {
    "stt": "speech_to_text",
    "translate": "text_translation",
    "retranslate": "text_translation",
    "tts": "text_to_speech",
    "dub": "video_translation",
    "subtitle": "subtitle_translation",
}


def empty_capabilities() -> dict[str, None]:
    """Dict đủ 18 key, giá trị None — trạng thái "chưa biết gì" của model mới."""
    return {c: None for c in CAPABILITIES}


def feature_stage(feature_key: str) -> str | None:
    """Công đoạn pipeline gắn với feature (ngược của STAGE_FEATURES), hoặc None."""
    for stage, f in STAGE_FEATURES.items():
        if f == feature_key:
            return stage
    return None
