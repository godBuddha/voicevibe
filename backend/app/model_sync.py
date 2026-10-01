"""Model Sync — Pull models từ provider → chuẩn hoá → nhận diện capability → upsert registry.

Workflow (yêu cầu thiết kế, mỗi bước nằm trong hàm riêng để test được):
    Provider API → fetch_provider_models()
                  → _normalize_openrouter / _normalize_openai_generic / _normalize_ollama
                  → (detect capabilities — trong từng _normalize, CHỈ từ metadata chính thức)
                  → sync_provider() = compute_compatibility + upsert theo (provider_id, model_id)
                  → xoá model vắng mặt + gỡ gán stage đang trỏ tới
                  → trả thống kê {added, updated, removed, ...}

Ba quy tắc cưỡng chế:
1. KHÔNG suy đoán capability từ tên model (gpt → chat, whisper → STT là sai).
   Chỉ dùng metadata chính thức; không khai báo → None → model dừng ở "unknown".
2. Idempotent: bấm Sync bao nhiêu lần cũng không duplicate — danh tính là cặp
   (provider_id, model_id); update KHÔNG đụng cờ `enabled` của admin.
3. Model bị nhà cung cấp gỡ khỏi danh sách → XOÁ khỏi registry (quyết định đã
   chốt), kèm gỡ gán `stage_models` đang trỏ tới để pipeline rơi về cấu hình
   kế tiếp (fallback → settings → local) thay vì gọi model đã không còn.
"""
from __future__ import annotations

import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .capabilities import CAPABILITIES, empty_capabilities
from .compat import compute_compatibility
from .models import AiModel, AiProvider, StageModel, PROVIDER_OPENAI, PROVIDER_OLLAMA

TIMEOUT = httpx.Timeout(20.0, connect=8.0)
SHOW_TIMEOUT = httpx.Timeout(3.0, connect=3.0)  # fallback /api/show per-model (Ollama cũ)


class SyncError(Exception):
    """Fetch gốc thất bại (mạng/HTTP/JSON) — endpoint quy thành 502, DB nguyên vẹn."""

# Cắt description khi lưu — model description của OpenRouter có thể rất dài,
# registry không cần cả bài giới thiệu.
_DESC_MAX = 2000


# --------------------------------------------------------------------- fetch
def fetch_provider_models(p: AiProvider) -> tuple[list, dict]:
    """Lấy danh sách model thô từ provider. Lỗi I/O → SyncError (endpoint quy
    thành 502, DB không ghi gì — bấm Sync lại được). Trả (items_raw, info)."""
    base = p.base_url.rstrip("/")
    try:
        if p.kind == PROVIDER_OLLAMA:
            r = httpx.get(f"{base}/api/tags", timeout=TIMEOUT)
            r.raise_for_status()
            return list(r.json().get("models") or []), {}
        # `_headers` nằm ở providers_api; import tại chỗ dùng vì providers_api
        # import module này (endpoint sync) — import ngược ở top-level là vòng.
        from .providers_api import _headers
        r = httpx.get(f"{base}/models", headers=_headers(p), timeout=TIMEOUT)
        r.raise_for_status()
        return list(r.json().get("data") or []), {}
    except httpx.HTTPError as exc:
        raise SyncError(f"không kết nối được provider: {exc.__class__.__name__}") from exc
    except ValueError as exc:
        raise SyncError("phản hồi không phải JSON hợp lệ") from exc


# ------------------------------------------------------------------ normalize
def _modality_split(raw) -> tuple[list | None, list | None]:
    """Chuẩn hoá modality thành (input, output).

    OpenRouter trả `architecture.modality` dạng chuỗi "text+image->text" và
    (mới hơn) `input_modalities`/`output_modalities` dạng mảng. Nếu chỉ có chuỗi
    thì tự tách; không dấu "->" coi như chỉ có input side.
    """
    if isinstance(raw, list):
        return raw, None  # mảng input_modalities; output lấy ở key khác
    if isinstance(raw, str):
        if "->" in raw:
            lhs, rhs = raw.split("->", 1)
            return [t for t in lhs.split("+") if t], [t for t in rhs.split("+") if t]
        return [t for t in raw.split("+") if t], None
    return None, None


def _normalize_openrouter(m: dict, errors: list[str]) -> dict:
    """Metadata ĐẦY ĐỦ kiểu OpenRouter — nguồn chính thức cho mọi capability."""
    arch = m.get("architecture") or {}
    in_mods, out_mods = arch.get("input_modalities"), arch.get("output_modalities")
    if in_mods is None and out_mods is None and arch.get("modality"):
        # Chuỗi modality cũ "text+image->text" — tách theo dấu "->"; không dấu
        # "->" coi như chỉ có input side.
        in_mods, out_mods = _modality_split(arch.get("modality"))

    caps = empty_capabilities()

    def _mark(mods, side: str) -> None:
        if mods is None:
            return
        for tok in mods:
            if side == "in":
                if tok == "text":
                    caps["text"] = True
                elif tok == "audio":
                    caps["audioInput"] = True
                elif tok == "image":
                    caps["vision"] = True
                    caps["imageUnderstanding"] = True
                elif tok == "video":
                    caps["videoInput"] = True
            else:
                if tok == "text":
                    caps["text"] = True
                    caps["chat"] = True
                elif tok == "audio":
                    caps["audioOutput"] = True
                elif tok == "image":
                    caps["imageGeneration"] = True
                elif tok == "video":
                    caps["videoGeneration"] = True
            # token lạ ("file"...) → bỏ qua, không suy đoán

    _mark(in_mods, "in")
    _mark(out_mods, "out")
    # Mảng modality là DANH SÁCH ĐẦY ĐỦ: token vắng = provider xác nhận KHÔNG có
    # → False. Đây là nguồn của giá trị False trung thực (incompatible chính xác),
    # không phải đoán từ tên model.
    if in_mods is not None:
        for cap, tok in (("videoInput", "video"), ("audioInput", "audio"),
                         ("vision", "image"), ("imageUnderstanding", "image")):
            if caps[cap] is None:
                caps[cap] = tok in in_mods
    if out_mods is not None:
        for cap, tok in (("videoGeneration", "video"), ("imageGeneration", "image"),
                         ("audioOutput", "audio")):
            if caps[cap] is None:
                caps[cap] = tok in out_mods
    # out không có "text" trong mảng đã khai → model không sinh text
    if out_mods is not None and caps["chat"] is None:
        caps["chat"] = False
        caps["text"] = False

    sp = m.get("supported_parameters")
    if sp is not None:
        caps["functionCalling"] = any(k in sp for k in ("tools", "tool_choice", "parallel_tool_calls"))
        caps["structuredOutput"] = any(k in sp for k in ("structured_outputs", "response_format"))
        caps["reasoning"] = any(k in sp for k in ("reasoning", "reasoning_effort", "include_reasoning"))
        if caps["chat"] is True:
            caps["streaming"] = True  # chat model trên API chuẩn luôn stream

    top = m.get("top_provider") or {}
    pricing = None
    p = m.get("pricing") or {}
    try:
        pricing = {"input": float(p.get("prompt")), "output": float(p.get("completion")),
                   "currency": "USD"}
    except (TypeError, ValueError):
        pricing = None

    model_id = m.get("id") or ""
    source = "official" if (in_mods is not None or out_mods is not None or sp is not None) else "none"
    metadata = {k: m.get(k) for k in ("tokenizer", "instruct_type", "created", "canonical_slug")
                if m.get(k) is not None}
    return {
        "model_id": model_id,
        "display_name": (m.get("name") or model_id)[:255] or None,
        "description": ((m.get("description") or "")[:_DESC_MAX] or None),
        "org": model_id.split("/", 1)[0] if "/" in model_id else None,
        "capabilities": caps,
        "capability_source": source,
        "context_window": m.get("context_length") or top.get("context_length"),
        "input_token_limit": None,  # không nhà cung cấp nào khai — không suy đoán
        "output_token_limit": top.get("max_completion_tokens"),
        "pricing": pricing,
        "metadata": metadata,
        "last_synced_at": None,  # sync_provider gán
    }


def _normalize_openai_generic(m: dict, errors: list[str]) -> dict:
    """OpenAI chuẩn (api.openai.com, DeepSeek, vLLM...): `data[].id` là tất cả.

    KHÔNG có metadata capability → mọi cờ = None → model dừng ở "unknown".
    Đây chính là ý "không đủ metadata thì không tự suy đoán" của yêu cầu.
    """
    model_id = m.get("id") or ""
    return {
        "model_id": model_id,
        "display_name": model_id or None,
        "description": None,
        "org": None,
        "capabilities": empty_capabilities(),
        "capability_source": "none",
        "context_window": None,
        "input_token_limit": None,
        "output_token_limit": None,
        "pricing": None,
        "metadata": {k: m.get(k) for k in ("owned_by", "created") if m.get(k) is not None},
        "last_synced_at": None,
    }


def _ollama_show_caps(base: str, name: str) -> list | None:
    """Ollama cũ (<0.4) không trả `capabilities` trong /api/tags → hỏi /api/show."""
    try:
        r = httpx.post(f"{base}/api/show", json={"model": name}, timeout=SHOW_TIMEOUT)
        if r.status_code != 200:
            return None
        return r.json().get("capabilities") or None
    except httpx.HTTPError:
        return None


def _normalize_ollama(m: dict, errors: list[str], base: str) -> dict:
    name = m.get("name") or m.get("model") or ""
    raw_caps = m.get("capabilities")
    if raw_caps is None:  # Ollama cũ — fallback từng model, lỗi 1 model không chết sync
        raw_caps = _ollama_show_caps(base, name)
        if raw_caps is None:
            errors.append(f"{name}: không đọc được capability (/api/show)")
    caps = empty_capabilities()
    if raw_caps:
        if "completion" in raw_caps:
            caps["text"] = True
            caps["chat"] = True
            caps["streaming"] = True
        if "vision" in raw_caps:
            caps["vision"] = True
            caps["imageUnderstanding"] = True
        if "tools" in raw_caps:
            caps["functionCalling"] = True
        if "thinking" in raw_caps:
            caps["reasoning"] = True
        if "embedding" in raw_caps:
            caps["embeddings"] = True
        # chuỗi lạ → giữ nguyên trong metadata, capability để None
    det = m.get("details") or {}
    metadata = {"parameter_size": det.get("parameter_size"),
                "quantization_level": det.get("quantization_level"),
                "size": m.get("size"), "family": det.get("family"),
                "capabilities_raw": list(raw_caps) if raw_caps else None}
    metadata = {k: v for k, v in metadata.items() if v is not None}
    return {
        "model_id": name,
        "display_name": name or None,
        "description": None,
        "org": None,
        "capabilities": caps,
        "capability_source": "official" if raw_caps else "none",
        "context_window": det.get("context_length"),
        "input_token_limit": None,
        "output_token_limit": None,
        "pricing": None,
        "metadata": metadata,
        "last_synced_at": None,
    }


def _normalize(p: AiProvider, raw: list, errors: list[str]) -> list[dict]:
    """Chọn nhánh normalize. Kind `openai` phân theo HÌNH payload (không theo host)
    — OpenRouter-style có architecture/supported_parameters, còn lại là generic."""
    if p.kind == PROVIDER_OLLAMA:
        base = p.base_url.rstrip("/")
        return [_normalize_ollama(m, errors, base) for m in raw]
    is_rich = any(("architecture" in m or "supported_parameters" in m) for m in raw)
    if is_rich:
        return [_normalize_openrouter(m, errors) for m in raw]
    return [_normalize_openai_generic(m, errors) for m in raw]


# ---------------------------------------------------------------------- sync
def sync_provider(db: Session, p: AiProvider) -> dict:
    """Workflow chính: fetch → normalize → compatibility → upsert/xoá → commit.

    Chỉnh `enabled` của row CŨ là việc của admin (PATCH /models/{id}) — sync
    tuyệt đối không đụng, nên cấm Async phải chọn lại sau mỗi lần bấm Sync.
    """
    t0 = time.monotonic()
    errors: list[str] = []
    raw, _info = fetch_provider_models(p)
    drafts: dict[str, dict] = {}
    for n in _normalize(p, raw, errors):
        if not n["model_id"]:
            errors.append("(model thiếu id — bỏ qua)")
            continue
        drafts[n["model_id"]] = n  # dict thay list: trùng id tự gộp, không duplicate

    existing = {r.model_id: r for r in
                db.scalars(select(AiModel).where(AiModel.provider_id == p.id)).all()}
    now = int(time.time())
    added = updated = removed = 0
    for mid, n in drafts.items():
        row = existing.get(mid)
        payload = {**n, "last_synced_at": now,
                   "compatibility": compute_compatibility(n["capabilities"])}
        if row is None:
            db.add(AiModel(provider_id=p.id, enabled=True, **payload))
            added += 1
        else:
            for k, v in payload.items():
                setattr(row, k, v)
            updated += 1
    for mid, row in existing.items():
        if mid not in drafts:
            # upstream gỡ model → xoá + gỡ gán stage đang trỏ (primary biến mất
            # thì chain tự rơi về fallback → settings → local — đã kiểm đường rơi).
            for sm in db.scalars(select(StageModel).where(
                    StageModel.provider_id == p.id, StageModel.model == mid)).all():
                db.delete(sm)
            db.delete(row)
            removed += 1
    db.commit()
    return {
        "provider_id": p.id, "kind": p.kind, "synced": len(drafts),
        "added": added, "updated": updated, "removed": removed,
        "duration_ms": int((time.monotonic() - t0) * 1000),
        "errors": errors,
    }
