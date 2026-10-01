"""Day 5: translation stage — provider chain (cloud OpenAI-compatible or local Marian).

Cấu hình đọc theo thứ tự ưu tiên:
  1. **Công đoạn** trong /admin → bảng `stage_models` (provider + model, có chuỗi fallback)
  2. Setting `translate.*` (cách cấu hình cũ, vẫn hoạt động — không phá deployment đang chạy)
  3. Không có gì → opus-mt local (Apache-2.0)

Prompt hệ thống lấy từ bảng `prompts` (sửa được trong /admin), mặc định nằm trong code —
xem app/prompts.py.

Offline selftest (no model downloads):
  PYTHONPATH=. python -m app.pipelines.translate --selftest
"""
from __future__ import annotations

import os

from .. import prompts as P
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
    """OpenAI-compatible chat endpoint (cloud hoặc local vLLM/Ollama) qua provider layer.

    Prompt hệ thống lấy từ bảng `prompts` (task_key='translate') nên sửa được trong /admin
    mà không phải deploy lại — xem app/prompts.py.
    """

    def __init__(self, base_url: str, api_key: str, model: str,
                 source: str, target: str, system_prompt: str | None = None):
        from ..providers.openai_compat import OpenAIChatProvider

        self._chat = OpenAIChatProvider(base_url, api_key, model)
        self.source, self.target = source, target
        self._system_override = system_prompt

    @property
    def system(self) -> str:
        if self._system_override is not None:
            return self._system_override
        return P.render("translate", source=self.source, target=self.target)

    def translate(self, text: str) -> str:
        return self._chat.complete(self.system, text, max_tokens=512).strip()

    def retranslate_shorter(self, text: str, max_chars: int) -> str:
        """Dịch lại ngắn hơn cho đoạn vượt thời lượng — dùng prompt 'retranslate_timing'."""
        prompt = P.render("retranslate_timing", source=self.source, target=self.target,
                          text=text, max_chars=max_chars)
        return self._chat.complete("", prompt, max_tokens=512).strip()


def stage_translator(source: str, target: str):
    """Translator dựng từ cấu hình công đoạn trong /admin (nếu có).

    Trả None khi công đoạn 'translate' chưa được gán — caller rơi về đường cũ
    (`translate.*` settings / opus-mt local).

    Bọc try/except rộng: hàm này chạy trong worker, và một DB chưa migrate hoặc
    thiếu bảng KHÔNG được làm chết cả pipeline — cứ rơi về đường cũ là đúng.
    """
    try:
        from ..db import SessionLocal
        from ..providers_api import stage_chain

        with SessionLocal() as db:
            chain = stage_chain("translate", db)
    except Exception:  # noqa: BLE001
        return None
    if not chain:
        return None

    def _make(entry: dict) -> "CloudChatTranslator":
        base = entry["base_url"].rstrip("/")
        if entry["kind"] != "openai":
            # Ollama cũng nói được chuẩn OpenAI ở /v1 — quy về cùng một provider.
            base = base + "/v1"
        return CloudChatTranslator(base, entry["api_key"], entry["model"], source, target)

    first = _make(chain[0])
    if len(chain) == 1:
        return first
    # Chuỗi fallback (order>0): trước đây chỉ chain[0] được dùng, các entry dự
    # phòng là cấu hình chết. ProviderChain thử lần lượt — hỏng entry nào thì
    # qua entry kế, hết chuỗi thì job failed với lỗi gộp (đúng ngữ nghĩa
    # "cấu hình xong nhưng chết thì phải fail rõ").
    from ..providers.registry import ProviderChain
    return ChainTranslator(ProviderChain([_make(e) for e in chain]))


class ChainTranslator:
    """Bọc ProviderChain theo interface của mọi translator (translate /
    retranslate_shorter) — dùng được ở mọi nơi build_translator trả về."""

    def __init__(self, chain):
        self._chain = chain

    def translate(self, text: str) -> str:
        return self._chain.call("translate", text)

    def retranslate_shorter(self, text: str, max_chars: int) -> str:
        return self._chain.call("retranslate_shorter", text, max_chars)


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
    """Translator cho một cặp ngôn ngữ, theo thứ tự: công đoạn → settings → local."""
    staged = stage_translator(source, target)
    if staged is not None:
        return staged
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

    # Prompt lấy từ bảng `prompts` (sửa được trong /admin), không hardcode trong class.
    t2 = CloudChatTranslator("http://mock/v1", "k", "m", "vi", "en")
    assert "from vi to en" in t2.system, t2.system
    t3 = CloudChatTranslator("http://mock/v1", "k", "m", "vi", "en",
                             system_prompt="DỊCH NGẮN GỌN")
    assert t3.system == "DỊCH NGẮN GỌN", "prompt override không được tôn trọng"
    print("prompt đọc từ bảng prompts .. OK")
    print("TRANSLATE SELFTEST PASSED")


if __name__ == "__main__":
    _selftest()
