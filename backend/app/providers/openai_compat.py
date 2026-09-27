"""OpenAI-compatible HTTP providers (chat / tts / stt).

Works with anything speaking the OpenAI wire format:
  OpenAI, DeepSeek, Groq, Together, Fireworks, OpenRouter,
  local vLLM / SGLang / llama.cpp servers, VieNeu's /v1/audio/speech, ...

Limits of the OpenAI standard (why some stages stay local):
  - /v1/audio/speech = PRESET voices only. Zero-shot voice cloning is NOT
    part of the standard -> cloning stays local (VieNeu / Chatterbox) unless
    the endpoint implements an extension (e.g. VieNeu's POST /v1/voices).
  - /v1/audio/transcriptions returns text+timestamps, NO speaker labels
    -> diarization stays local (pyannote).
"""
from __future__ import annotations

from time import sleep as _sleep

import httpx

from .base import TranscriptSegment

RETRY_STATUS = {429, 500, 502, 503, 504}


class _Retryable(Exception):
    pass


class OpenAIBase:
    def __init__(self, base_url: str, api_key: str, model: str, *,
                 timeout: float = 120.0, max_retries: int = 2,
                 client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_retries = max_retries
        self._client = client or httpx.Client(timeout=timeout)
        self._headers = {"Authorization": f"Bearer {api_key}"}

    def _post(self, path: str, json_body: dict | None = None, *,
              data: dict | None = None, files: dict | None = None) -> httpx.Response:
        url = f"{self.base_url}{path}"
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                r = self._client.post(url, headers=self._headers, json=json_body,
                                      data=data, files=files)
                if r.status_code in RETRY_STATUS:
                    last = _Retryable(f"HTTP {r.status_code}: {r.text[:200]}")
                elif r.status_code >= 400:
                    raise RuntimeError(f"{url} -> HTTP {r.status_code}: {r.text[:200]}")
                else:
                    return r
            except httpx.HTTPError as exc:  # connect/timeout/reset
                last = exc
            if attempt < self.max_retries:
                _sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"exhausted retries for {url}") from last


class OpenAIChatProvider(OpenAIBase):
    """POST /v1/chat/completions — translation & any LLM step."""

    def complete(self, system: str, user: str, *, json_mode: bool = False,
                 max_tokens: int = 2048) -> str:
        body: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        data = self._post("/chat/completions", body).json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"unexpected chat response shape: {str(data)[:200]}") from exc


class OpenAITTSProvider(OpenAIBase):
    """POST /v1/audio/speech — OpenAI tts-1 / gpt-4o-mini-tts, VieNeu server, ...

    Preset voices only (see module docstring for the cloning caveat).
    """

    def synthesize(self, text: str, voice: str | None = None,
                   response_format: str = "wav") -> bytes:
        body = {
            "model": self.model,
            "input": text,
            "voice": voice or "alloy",
            "response_format": response_format,
        }
        return self._post("/audio/speech", body).content


class OpenAISTTProvider(OpenAIBase):
    """POST /v1/audio/transcriptions — whisper-1 / gpt-4o-transcribe compatible.

    verbose_json -> segments with timestamps. Speaker labels are NOT part of
    the standard; diarization is a separate local stage (pyannote).
    """

    def transcribe(self, audio_path: str, language: str | None = None) -> list[TranscriptSegment]:
        data: dict = {"model": self.model, "response_format": "verbose_json"}
        if language:
            data["language"] = language
        with open(audio_path, "rb") as f:
            files = {"file": (audio_path.rsplit("/", 1)[-1], f, "audio/wav")}
            j = self._post("/audio/transcriptions", None, data=data, files=files).json()
        segs = j.get("segments") or []
        return [
            TranscriptSegment(
                start=float(s.get("start", 0.0)),
                end=float(s.get("end", 0.0)),
                text=(s.get("text") or "").strip(),
            )
            for s in segs
        ]
