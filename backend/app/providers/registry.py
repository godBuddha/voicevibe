"""Config-driven provider registry with fallback chains.

Example stage config (env var names, never literal keys):

  translation:
    - provider: openai_chat
      base_url: https://api.deepseek.com/v1
      api_key_env: DEEPSEEK_API_KEY
      model: deepseek-chat
    - provider: openai_chat          # fallback: local vLLM serving Qwen
      base_url: http://vllm:8000/v1
      api_key: EMPTY
      model: Qwen/Qwen3-4B-Instruct-2507

  tts_vi:
    - provider: local_vieneu         # cloning — must be local (Apache-2.0)
    - provider: openai_tts           # fallback: preset voices only
      base_url: https://api.openai.com/v1
      api_key_env: OPENAI_API_KEY
      model: tts-1
"""
from __future__ import annotations

import os
from typing import Any, Callable

import httpx

from .openai_compat import OpenAIChatProvider, OpenAISTTProvider, OpenAITTSProvider

_OPENAI_TYPES: dict[str, type] = {
    "openai_chat": OpenAIChatProvider,
    "openai_tts": OpenAITTSProvider,
    "openai_stt": OpenAISTTProvider,
}

_LOCAL_FACTORIES: dict[str, Callable[[], Any]] = {}


def _local_factory(name: str) -> Callable[[], Any]:
    if name not in _LOCAL_FACTORIES:
        def make() -> Any:
            if name == "local_vieneu":
                from .local import LocalVieneuTTSProvider
                return LocalVieneuTTSProvider()
            if name == "local_whisper":
                from .local import LocalWhisperSTTProvider
                return LocalWhisperSTTProvider()
            raise ValueError(f"unknown local provider: {name}")
        _LOCAL_FACTORIES[name] = make
    return _LOCAL_FACTORIES[name]


class LazyProvider:
    """Delays heavy local engine init until first call — chain build stays cheap,
    and a missing engine becomes a *fallback* event instead of a boot failure."""

    def __init__(self, factory: Callable[[], Any]):
        object.__setattr__(self, "_factory", factory)
        object.__setattr__(self, "_instance", None)

    def __getattr__(self, name: str):
        instance = object.__getattribute__(self, "_instance")
        if instance is None:
            instance = object.__getattribute__(self, "_factory")()
            object.__setattr__(self, "_instance", instance)
        return getattr(instance, name)


def _resolve_api_key(cfg: dict) -> str:
    env = cfg.get("api_key_env")
    return os.getenv(env, "") if env else cfg.get("api_key", "")


class ProviderChain:
    """Try providers in order; first success wins, last error is re-raised."""

    def __init__(self, providers: list):
        self.providers = providers

    def call(self, method: str, *args, **kwargs):
        last_exc: Exception | None = None
        for p in self.providers:
            try:
                return getattr(p, method)(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 — any failure -> next provider
                last_exc = exc
        raise RuntimeError(
            f"all {len(self.providers)} provider(s) failed for {method}()"
        ) from last_exc


def build_chain(stage_cfg: list[dict],
                client_factory: Callable[[], httpx.Client] | None = None) -> ProviderChain:
    providers: list = []
    for entry in stage_cfg:
        kind = entry["provider"]
        if kind in _OPENAI_TYPES:
            client = client_factory() if client_factory else None
            providers.append(_OPENAI_TYPES[kind](
                base_url=entry["base_url"],
                api_key=_resolve_api_key(entry),
                model=entry["model"],
                client=client,
            ))
        elif kind.startswith("local_"):
            providers.append(LazyProvider(_local_factory(kind)))
        else:
            raise ValueError(f"unknown provider type: {kind}")
    return ProviderChain(providers)
