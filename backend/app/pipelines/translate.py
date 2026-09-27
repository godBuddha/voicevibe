"""Day 5: translation stage — provider chain (cloud OpenAI-compatible or local Marian).

Config (env for now — D6 Settings UI takes over):
  TRANSLATE_BASE_URL + TRANSLATE_API_KEY + TRANSLATE_MODEL -> cloud chat provider
  otherwise                                                -> local opus-mt (Apache-2.0)

Offline selftest (no model downloads):
  PYTHONPATH=. python -m app.pipelines.translate --selftest
"""
from __future__ import annotations

import os

from ..settings_service import get_setting

_MARIAN = {
    ("vi", "en"): "Helsinki-NLP/opus-mt-vi-en",
    ("en", "vi"): "Helsinki-NLP/opus-mt-en-vi",
}


class LocalMarianTranslator:
    """Tiny seq2seq translator (~300MB) — GPU or CPU, Apache-2.0."""

    def __init__(self, source: str, target: str, device: str = "auto"):
        model_id = _MARIAN.get((source, target))
        if model_id is None:
            raise ValueError(
                f"no local Marian model for {source}->{target}; "
                "configure a cloud chat provider (TRANSLATE_* env / Settings UI)"
            )
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_id).eval()
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = self.model.to(device)
        self.device = device

    def translate(self, text: str) -> str:
        import torch

        with torch.no_grad():
            inputs = self.tok(text, return_tensors="pt", truncation=True,
                              max_length=512).to(self.device)
            out = self.model.generate(**inputs, max_new_tokens=512, num_beams=4)
        return self.tok.decode(out[0], skip_special_tokens=True).strip()


class CloudChatTranslator:
    """OpenAI-compatible chat endpoint (cloud or local vLLM) via provider layer."""

    def __init__(self, base_url: str, api_key: str, model: str,
                 source: str, target: str):
        from ..providers.openai_compat import OpenAIChatProvider

        self._chat = OpenAIChatProvider(base_url, api_key, model)
        self.system = (
            f"You are a professional subtitle translator. Translate each line "
            f"from {source} to {target}. Keep it short and natural — it will be "
            f"spoken aloud. Reply with the translation only."
        )

    def translate(self, text: str) -> str:
        return self._chat.complete(self.system, text, max_tokens=512).strip()


def _cloud_cfg() -> tuple[str, str, str] | None:
    """Cloud chat config — Settings DB first, env fallback for dev bootstrap."""
    base = get_setting("translate.base_url", env_fallback="TRANSLATE_BASE_URL")
    key = get_setting("translate.api_key", env_fallback="TRANSLATE_API_KEY")
    model = get_setting("translate.model", env_fallback="TRANSLATE_MODEL")
    if base and key and model:
        return str(base), str(key), str(model)
    return None


def _pick_backend(source: str, target: str) -> str:
    pref = str(get_setting("translate.backend", "auto")).lower()
    cloud = _cloud_cfg()
    if pref == "cloud":
        if not cloud:
            raise ValueError(
                "translate.backend=cloud nhưng thiếu base_url/api_key/model (Settings UI)")
        return "cloud"
    if pref == "local":
        if (source, target) not in _MARIAN:
            raise ValueError(f"no local Marian model for {source}->{target}")
        return "local"
    # auto: cloud nếu đã cấu hình, иначе local
    if cloud:
        return "cloud"
    if (source, target) in _MARIAN:
        return "local"
    raise ValueError(
        f"no translator for {source}->{target}: cấu hình cloud trong Settings UI "
        "hoặc dùng cặp ngôn ngữ có model local"
    )


def build_translator(source: str, target: str):
    backend = _pick_backend(source, target)
    if backend == "cloud":
        base, key, model = _cloud_cfg()  # type: ignore[misc]
        return CloudChatTranslator(base, key, model, source, target)
    return LocalMarianTranslator(source, target)


def _selftest() -> None:
    import httpx

    from ..providers.openai_compat import OpenAIChatProvider  # noqa: F401

    def mock_client(handler):
        return httpx.Client(transport=httpx.MockTransport(handler))

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v1/chat/completions"
        body = __import__("json").loads(req.content)
        return httpx.Response(200, json={"choices": [
            {"message": {"content": "Hello everyone, I am Long."}}]})

    os.environ["TRANSLATE_BASE_URL"] = "http://mock/v1"
    os.environ["TRANSLATE_API_KEY"] = "k"
    os.environ["TRANSLATE_MODEL"] = "test-model"
    assert _pick_backend("vi", "en") == "cloud"
    t = build_translator("vi", "en")
    assert isinstance(t, CloudChatTranslator)
    t._chat._client = mock_client(handler)
    assert t.translate("Xin chào các bạn, mình là Long.") == "Hello everyone, I am Long."

    for k in ("TRANSLATE_BASE_URL", "TRANSLATE_API_KEY", "TRANSLATE_MODEL"):
        os.environ.pop(k)
    assert _pick_backend("vi", "en") == "local"
    try:
        _pick_backend("vi", "fr")
        raise AssertionError("should have raised")
    except ValueError:
        pass

    print("cloud path (mock) .......... OK")
    print("local fallback pick ........ OK")
    print("unsupported dir raises ..... OK")
    print("TRANSLATE SELFTEST PASSED")


if __name__ == "__main__":
    _selftest()
