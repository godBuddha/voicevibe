"""B5 — catalog + registry TTS: 3 backend (local VieNeu / edge / cloud).

Vì sao tách file riêng thay vì nhét vào registry.py: registry.py là
ProviderChain của DỊCH (translate) — nhét TTS vào là hai ý tưởng trong một
file, sai khi về sau translate cần tối ưu riêng. Catalog trả về cho UI:
giọng mỗi backend + nhà máy dựng engine.

Hợp đồng voice_id ("lớp đọc" — quyết định D7 của kế hoạch B):
    "edge:vi-VN-HoaiMyNeural"  →  (backend="edge",   voice="vi-VN-HoaiMyNeural")
    "cloud:alloy"              →  (backend="cloud",  voice="alloy")
    "Hải Đăng" (không dấu :)   →  ("local", "Hải Đăng")   ← LEGACY: tên giọng
                                   preset VieNeu và id giọng clone (hex uid)
                                   không có dấu ":" → job cũ + trang Voices
                                   KHÔNG vỡ. Không có "local:" prefix hợp lệ
                                   — để tránh chạm trán id clone (hex).
Namespace lạ ("gpt:"...) → ValueError → create_job 422.
"""
from __future__ import annotations

from .base import TTSVoice

# ------------------------------------------------------------------ catalog
# local = VieNeu preset (khớp tên engine trả về — PRESET_ROTATION cũ). edge =
# giọng Microsoft (danh sách thật từ list_voices; hai giọng vi dưới là điểm
# khởi đầu cho dropdown không mạng). cloud = OpenAI-compatible preset voices.
PRESET_VOICES: dict[str, list[TTSVoice]] = {
    "local": [
        TTSVoice(code="Hải Đăng", name="Hải Đăng — nữ, sáng", language="vi",
                 gender="female", provider="local", kind="preset",
                 recommended=True),
        TTSVoice(code="Mai Anh", name="Mai Anh — nữ, dịu", language="vi",
                 gender="female", provider="local", kind="preset"),
        TTSVoice(code="Quang Sơn", name="Quang Sơn — nam, trầm", language="vi",
                 gender="male", provider="local", kind="preset"),
        TTSVoice(code="Thùy Dung", name="Thùy Dung — nữ, tự nhiên", language="vi",
                 gender="female", provider="local", kind="preset"),
    ],
    "edge": [
        TTSVoice(code="vi-VN-HoaiMyNeural", name="Hà My — nữ (Microsoft, miễn phí qua mạng)",
                 language="vi", gender="female", provider="edge", kind="preset",
                 recommended=True),
        TTSVoice(code="vi-VN-NamMinhNeural", name="Nam Minh — nam (Microsoft, miễn phí qua mạng)",
                 language="vi", gender="male", provider="edge", kind="preset"),
    ],
    "cloud": [
        TTSVoice(code="alloy", name="Alloy", language="en", gender="neutral",
                 provider="cloud", kind="preset"),
        TTSVoice(code="echo", name="Echo", language="en", gender="neutral",
                 provider="cloud", kind="preset"),
        TTSVoice(code="fable", name="Fable", language="en", gender="neutral",
                 provider="cloud", kind="preset"),
        TTSVoice(code="onyx", name="Onyx", language="en", gender="neutral",
                 provider="cloud", kind="preset"),
        TTSVoice(code="nova", name="Nova", language="en", gender="neutral",
                 provider="cloud", kind="preset"),
        TTSVoice(code="shimmer", name="Shimmer", language="en", gender="neutral",
                 provider="cloud", kind="preset"),
    ],
}

BACKENDS = ("local", "edge", "cloud")


def parse_voice_ref(ref: str | None) -> tuple[str, str | None]:
    """voice_id → (backend, voice-code). LEGACY: không dấu ':' → local."""
    if not ref:
        return "local", None
    if ":" in ref:
        backend, _, code = ref.partition(":")
        if backend not in BACKENDS:
            raise ValueError(
                f"giọng đọc không hợp lệ: '{ref}' — backend phải là một trong "
                f"{list(BACKENDS)}")
        return backend, code or None
    return "local", ref  # LEGACY — không phá job cũ / giọng clone (hex uid)


def rotate_preset(backend: str, i: int) -> str:
    """Xoay giọng cho dub đa người nói — thay PRESET_ROTATION cứng theo backend."""
    return PRESET_VOICES[backend][i % len(PRESET_VOICES[backend])].code


def build_tts(backend: str = "local"):
    """Nhà máy dựng engine theo backend. "cloud" đọc stage 'tts' (Model Hub)."""
    if backend == "local":
        from .local import LocalVieneuTTSProvider

        return LocalVieneuTTSProvider()
    if backend == "edge":
        from .edge import EdgeTTSEngine

        return EdgeTTSEngine()
    if backend == "cloud":
        from ..pipelines.tts import _cloud_tts
        from .openai_compat import OpenAITTSProvider

        cloud = _cloud_tts()
        if cloud is None:
            raise ValueError(
                "backend cloud cần gán model cho công đoạn TTS trong Model Hub "
                "trước (Admin → Model Hub → công đoạn TTS)")
        return OpenAITTSProvider(*cloud)
    raise ValueError(f"backend TTS không hợp lệ: {backend!r}")
