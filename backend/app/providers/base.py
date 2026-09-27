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
