"""Provider contracts — every pipeline stage is pluggable.

Design rule: LOCAL-FIRST, CLOUD-OPTIONAL.
  - Each stage (stt / translate / tts) has one interface.
  - Local engines (faster-whisper, pyannote, VieNeu, Qwen-on-vLLM) and
    OpenAI-compatible cloud endpoints implement the SAME interface.
  - The dub pipeline only knows the interface -> providers are swapped via
    config, zero code change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class TranscriptSegment:
    start: float          # seconds
    end: float
    text: str
    speaker: str | None = None   # diarization label; NOT part of OpenAI standard
    # A4: mốc thời gian THEO TỪNG TỪ (chỉ đường local faster-whisper bật
    # `word_timestamps` mới có; cloud STT / Marian không có → None). Dùng để
    # tách cue phụ đề dài đúng ranh giới từ với mốc giờ chính xác.
    words: "list[Word] | None" = None


@dataclass
class Word:
    """Một từ trong bản transcribe: mốc giờ riêng + chữ. (Port cấu trúc
    Word{Num,Text,Start,End} của KrillinAI — Num bỏ vì chỉ số Python tự có.)"""
    start: float
    end: float
    text: str


@runtime_checkable
class STTProvider(Protocol):
    def transcribe(self, audio_path: str, language: str | None = None) -> list[TranscriptSegment]: ...


@runtime_checkable
class ChatProvider(Protocol):
    def complete(self, system: str, user: str, *, json_mode: bool = False,
                 max_tokens: int = 2048) -> str: ...


@runtime_checkable
class TTSProvider(Protocol):
    def synthesize(self, text: str, voice: str | None = None) -> bytes: ...


# ---------------------------------------------------- B5 — interface 2 tầng
# Tầng 1 (TTSProvider phía trên) là HỢP ĐỒNG TỐI THIỂU mọi engine phải có — giữ
# nguyên từ trước đây (LocalVieneuTTSProvider / OpenAITTSProvider đã đúng shape).
# Tầng 2 (TTSEngine) là lớp MỞ RỘNG TÙY CHỌN — port TTSProvider (tầng 2) của
# OpenCreator internal/ttsprovider/provider.go: engine "đầy đủ" trả danh sách
# giọng + nhận options chi tiết (tốc độ, format, hướng dẫn đọc). Engine nào
# chưa implement tầng 2 thì pipeline chỉ dùng tầng 1 như cũ.

@dataclass
class TTSOptions:
    text: str
    voice: str | None = None
    speed: float = 1.0          # 1.0 = bình thường; 1.15 = nhanh hơn 15%
    format: str = "wav"
    ref_audio: str | None = None    # path clip tham khảo (clone) — tầng 2 chính thức hoá
    denoise: bool = True
    instructions: str | None = None  # hướng dẫn đọc (một số model gpt-4o-tts hỗ trợ)


@dataclass
class TTSVoice:
    """Một giọng trong catalog — port TTSVoice của OpenCreator (bỏ Scenario)."""
    code: str                   # code engine hiểu ("Hải Đăng", "vi-VN-HoaiMyNeural", "alloy")
    name: str                   # tên hiển thị
    language: str               # "vi", "vi-VN", "en"...
    gender: str                 # "male" | "female" | ""
    provider: str               # "local" | "edge" | "cloud"
    kind: str                   # "preset" | "clone"
    recommended: bool = False


@runtime_checkable
class TTSEngine(Protocol):
    """Tầng 2 — engine ĐẦY ĐỦ (tùy chọn implement)."""

    def synthesize_ex(self, opts: TTSOptions) -> bytes: ...
    def list_voices(self) -> list[TTSVoice]: ...
