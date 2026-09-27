"""API quản trị AI — nhà cung cấp (Cloud OpenAI-compatible + Ollama), công đoạn, prompt.

Ba quy tắc bảo mật/thiết kế được cưỡng chế ở đây, mỗi cái có test riêng:

1. **API key không bao giờ rời server.** `GET` chỉ trả `api_key_hint` (4 ký tự cuối) và
   cờ `api_key_set`. Ghi bằng PATCH semantics: trường vắng/null = giữ nguyên,
   chuỗi rỗng = xoá, có giá trị = thay. (Open WebUI trả key thô trong payload admin —
   đây là chỗ ta cố tình KHÔNG làm theo.)
2. **Mọi lời gọi ra ngoài phát xuất từ BACKEND**, không từ trình duyệt: key không đi qua
   client, và trình duyệt không cần thấy endpoint của nhà cung cấp.
3. **Kiểm tra kết nối là lời gọi nhẹ nhất có thể** — OpenAI: `GET {base}/models`;
   Ollama: `GET {base}/api/version` (rẻ hơn `/api/tags` và không tải danh sách model).

Ollama: ngoài kết nối + liệt kê, còn **tải model** (proxy stream `/api/pull` để UI hiện
tiến trình) và **xoá model** (`/api/delete`).
"""
from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import prompts as P
from .auth import current_admin
from .db import get_db
from .models import (
    AiProvider,
    PROVIDER_KINDS,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    STAGES,
    StageModel,
)
from .settings_service import _fernet  # dùng lại Fernet của settings (một nguồn khoá)

router = APIRouter(prefix="/v1/admin", tags=["admin-ai"])

TIMEOUT = httpx.Timeout(20.0, connect=8.0)


# --------------------------------------------------------------------- tiện ích
def _encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def _decrypt(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except Exception:  # noqa: BLE001 — đổi master key thì key cũ không đọc được
        return None


def _hint(value: str | None) -> str | None:
    if not value:
        return None
    return "••••" + value[-4:] if len(value) > 4 else "••••"


def _norm_base(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _out(p: AiProvider) -> dict:
    """Bản ghi an toàn để trả ra API — KHÔNG có key thật."""
    return {
        "id": p.id, "name": p.name, "kind": p.kind, "base_url": p.base_url,
        "enabled": p.enabled, "prefix_id": p.prefix_id,
        "api_key_set": bool(p.api_key_enc), "api_key_hint": p.api_key_hint,
        "created_at": p.created_at,
    }


def _get(db: Session, provider_id: str) -> AiProvider:
    p = db.get(AiProvider, provider_id)
    if p is None:
        raise HTTPException(status_code=404, detail="không tìm thấy nhà cung cấp")
    return p


def _headers(p: AiProvider) -> dict:
    key = _decrypt(p.api_key_enc)
    return {"Authorization": f"Bearer {key}"} if key else {}


def _chat_target(p: AiProvider) -> str:
    """Đích request thật — hiển thị làm helper text trong UI."""
    return f"{_norm_base(p.base_url)}/api/chat" if p.kind == PROVIDER_OLLAMA \
        else f"{_norm_base(p.base_url)}/chat/completions"


# ------------------------------------------------------------------- providers
class ProviderIn(BaseModel):
    name: str
    kind: str = PROVIDER_OPENAI
    base_url: str
    api_key: str | None = None      # PATCH semantics: vắng/rỗng/có giá trị
    prefix_id: str | None = None
    enabled: bool = True


class ProviderPatch(BaseModel):
    name: str | None = None
    kind: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    prefix_id: str | None = None
    enabled: bool | None = None


@router.get("/providers")
def list_providers(_: object = Depends(current_admin),
                   db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(AiProvider).order_by(AiProvider.created_at)).all()
    return {"providers": [_out(p) for p in rows]}


@router.post("/providers", status_code=201)
def create_provider(body: ProviderIn, _: object = Depends(current_admin),
                    db: Session = Depends(get_db)) -> dict:
    if body.kind not in PROVIDER_KINDS:
        raise HTTPException(status_code=422, detail=f"kind phải là {list(PROVIDER_KINDS)}")
    if not _norm_base(body.base_url):
        raise HTTPException(status_code=422, detail="base_url không được để trống")
    p = AiProvider(name=body.name.strip() or "Provider", kind=body.kind,
                   base_url=_norm_base(body.base_url),
                   prefix_id=(body.prefix_id or None), enabled=body.enabled)
    if body.api_key:
        p.api_key_enc = _encrypt(body.api_key)
        p.api_key_hint = _hint(body.api_key)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _out(p)


@router.patch("/providers/{provider_id}")
def patch_provider(provider_id: str, body: ProviderPatch,
                   _: object = Depends(current_admin),
                   db: Session = Depends(get_db)) -> dict:
    p = _get(db, provider_id)
    if body.name is not None:
        p.name = body.name.strip() or p.name
    if body.kind is not None:
        if body.kind not in PROVIDER_KINDS:
            raise HTTPException(status_code=422, detail=f"kind phải là {list(PROVIDER_KINDS)}")
        p.kind = body.kind
    if body.base_url is not None:
        if not _norm_base(body.base_url):
            raise HTTPException(status_code=422, detail="base_url không được để trống")
        p.base_url = _norm_base(body.base_url)
    if body.enabled is not None:
        p.enabled = body.enabled
    if body.prefix_id is not None:
        p.prefix_id = body.prefix_id or None
    # PATCH semantics cho bí mật: vắng = giữ nguyên, "" = xoá, có giá trị = thay.
    if body.api_key is not None:
        if body.api_key == "":
            p.api_key_enc = None
            p.api_key_hint = None
        else:
            p.api_key_enc = _encrypt(body.api_key)
            p.api_key_hint = _hint(body.api_key)
    db.commit()
    db.refresh(p)
    return _out(p)


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: str, _: object = Depends(current_admin),
                    db: Session = Depends(get_db)) -> dict:
    p = _get(db, provider_id)
    # Gỡ liên kết công đoạn trước khi xoá (FK có thể là NULL) để không còn trỏ vào hư không.
    for sm in db.scalars(select(StageModel).where(StageModel.provider_id == p.id)).all():
        db.delete(sm)
    db.delete(p)
    db.commit()
    return {"id": provider_id, "deleted": True}


# ------------------------------------------------------- kết nối & danh sách model
def _probe(p: AiProvider) -> dict:
    """Gọi kiểm tra nhẹ nhất. Không raise — trả dict để UI hiện được thông báo."""
    base = _norm_base(p.base_url)
    try:
        if p.kind == PROVIDER_OLLAMA:
            r = httpx.get(f"{base}/api/version", timeout=TIMEOUT)
            if r.status_code != 200:
                return {"ok": False, "detail": f"HTTP {r.status_code}: {r.text[:150]}"}
            return {"ok": True, "detail": f"Ollama {r.json().get('version', '?')}"}
        r = httpx.get(f"{base}/models", headers=_headers(p), timeout=TIMEOUT)
        if r.status_code != 200:
            return {"ok": False, "detail": f"HTTP {r.status_code}: {r.text[:150]}"}
        data = r.json().get("data") or []
        return {"ok": True, "detail": f"{len(data)} model khả dụng"}
    except httpx.HTTPError as exc:
        return {"ok": False, "detail": f"không kết nối được: {exc.__class__.__name__}"}
    except ValueError:
        return {"ok": False, "detail": "phản hồi không phải JSON hợp lệ"}


@router.post("/providers/{provider_id}/test")
def test_provider(provider_id: str, _: object = Depends(current_admin),
                  db: Session = Depends(get_db)) -> dict:
    p = _get(db, provider_id)
    return {"id": p.id, **_probe(p)}


@router.get("/providers/{provider_id}/models")
def provider_models(provider_id: str, _: object = Depends(current_admin),
                    db: Session = Depends(get_db)) -> dict:
    """Danh sách model: OpenAI `data[].id`; Ollama `models[]` (kèm dung lượng/số tham số)."""
    p = _get(db, provider_id)
    base = _norm_base(p.base_url)
    try:
        if p.kind == PROVIDER_OLLAMA:
            r = httpx.get(f"{base}/api/tags", timeout=TIMEOUT)
            r.raise_for_status()
            models = [{
                "name": m.get("name") or m.get("model", ""),
                "size": m.get("size"),
                "parameter_size": (m.get("details") or {}).get("parameter_size"),
                "quantization": (m.get("details") or {}).get("quantization_level"),
            } for m in (r.json().get("models") or [])]
        else:
            r = httpx.get(f"{base}/models", headers=_headers(p), timeout=TIMEOUT)
            r.raise_for_status()
            models = [{"name": m.get("id", "")} for m in (r.json().get("data") or [])]
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502,
                            detail=f"không lấy được danh sách model: {exc.__class__.__name__}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="phản hồi không phải JSON hợp lệ") from exc
    return {"provider_id": p.id, "kind": p.kind, "models": models}


# --------------------------------------------------------- Ollama: tải & xoá model
class PullIn(BaseModel):
    model: str


@router.post("/providers/{provider_id}/pull")
def pull_model(provider_id: str, body: PullIn, _: object = Depends(current_admin),
               db: Session = Depends(get_db)) -> StreamingResponse:
    """Proxy tiến trình tải model của Ollama (NDJSON) về cho UI.

    Ollama phát từng dòng JSON: {"status","total","completed"}; ta chuyển tiếp nguyên dạng
    để trình duyệt tự vẽ thanh tiến trình, không phải buffer cả GB trong RAM.
    """
    p = _get(db, provider_id)
    if p.kind != PROVIDER_OLLAMA:
        raise HTTPException(status_code=422, detail="chỉ Ollama mới tải model được")
    name = body.model.strip()
    if not name:
        raise HTTPException(status_code=422, detail="thiếu tên model")
    base = _norm_base(p.base_url)

    def stream():
        try:
            with httpx.stream("POST", f"{base}/api/pull",
                              json={"model": name, "stream": True},
                              timeout=httpx.Timeout(None, connect=8.0)) as r:
                if r.status_code != 200:
                    yield json.dumps({"status": "error",
                                      "detail": f"HTTP {r.status_code}"}) + "\n"
                    return
                for line in r.iter_lines():
                    if line:
                        yield line + "\n"
        except httpx.HTTPError as exc:
            yield json.dumps({"status": "error",
                              "detail": exc.__class__.__name__}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.delete("/providers/{provider_id}/models/{name:path}")
def delete_model(provider_id: str, name: str, _: object = Depends(current_admin),
                 db: Session = Depends(get_db)) -> dict:
    p = _get(db, provider_id)
    if p.kind != PROVIDER_OLLAMA:
        raise HTTPException(status_code=422, detail="chỉ Ollama mới xoá model được")
    base = _norm_base(p.base_url)
    try:
        r = httpx.request("DELETE", f"{base}/api/delete",
                          json={"model": name}, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502,
                            detail=f"không xoá được: {exc.__class__.__name__}") from exc
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=502, detail=f"HTTP {r.status_code}: {r.text[:150]}")
    return {"provider_id": p.id, "model": name, "deleted": True}


# ---------------------------------------------------------------------- công đoạn
class StageIn(BaseModel):
    provider_id: str | None = None
    model: str = ""
    params: dict | None = None
    order: int = 0


@router.get("/stages")
def list_stages(_: object = Depends(current_admin),
                db: Session = Depends(get_db)) -> dict:
    providers = {p.id: p for p in db.scalars(select(AiProvider)).all()}
    rows = db.scalars(select(StageModel).order_by(StageModel.stage, StageModel.order)).all()
    by_stage: dict[str, list[dict]] = {s: [] for s in STAGES}
    for r in rows:
        by_stage.setdefault(r.stage, []).append({
            "id": r.id, "provider_id": r.provider_id, "model": r.model,
            "params": r.params or {}, "order": r.order,
            "provider_name": providers[r.provider_id].name if r.provider_id in providers else None,
        })
    summary = {}
    for stage, items in by_stage.items():
        primary = next((i for i in items if i["order"] == 0), None)
        if primary and primary["provider_name"]:
            summary[stage] = f"{primary['model'] or '(mặc định)'} qua {primary['provider_name']}"
        elif stage == "translate":
            summary[stage] = "dùng cấu hình translate.* (Settings)"
        else:
            summary[stage] = "engine local mặc định"
    return {"stages": by_stage, "summary": summary}


@router.put("/stages/{stage}")
def set_stage(stage: str, body: StageIn, _: object = Depends(current_admin),
              db: Session = Depends(get_db)) -> dict:
    """Gán (provider, model) cho một công đoạn. order=0 ghi đè lựa chọn chính."""
    if stage not in STAGES:
        raise HTTPException(status_code=422, detail=f"stage phải thuộc {list(STAGES)}")
    if body.provider_id:
        _get(db, body.provider_id)  # 404 nếu không tồn tại
    row = db.scalar(select(StageModel).where(StageModel.stage == stage,
                                             StageModel.order == body.order))
    if row is None:
        row = StageModel(stage=stage, order=body.order)
        db.add(row)
    row.provider_id = body.provider_id
    row.model = body.model.strip()
    row.params = body.params or {}
    db.commit()
    return {"stage": stage, "provider_id": row.provider_id, "model": row.model,
            "order": row.order}


@router.delete("/stages/{stage}")
def clear_stage(stage: str, order: int = 0, _: object = Depends(current_admin),
                db: Session = Depends(get_db)) -> dict:
    row = db.scalar(select(StageModel).where(StageModel.stage == stage,
                                             StageModel.order == order))
    if row is not None:
        db.delete(row)
        db.commit()
    return {"stage": stage, "cleared": row is not None}


def stage_chain(stage: str, db: Session) -> list[dict]:
    """Chuỗi fallback của một công đoạn, đã giải mã key — dùng cho pipeline."""
    rows = db.scalars(select(StageModel).where(StageModel.stage == stage)
                      .order_by(StageModel.order)).all()
    out: list[dict] = []
    for r in rows:
        if not r.provider_id:
            continue
        p = db.get(AiProvider, r.provider_id)
        if p is None or not p.enabled:
            continue
        out.append({"kind": p.kind, "base_url": _norm_base(p.base_url),
                    "api_key": _decrypt(p.api_key_enc) or "",
                    "model": r.model, "params": r.params or {}})
    return out


# ------------------------------------------------------------------------ prompt
class PromptIn(BaseModel):
    content: str


@router.get("/prompts")
def list_prompts(_: object = Depends(current_admin)) -> dict:
    return {"prompts": P.list_prompts()}


@router.put("/prompts/{task_key}")
def put_prompt(task_key: str, body: PromptIn, _: object = Depends(current_admin)) -> dict:
    try:
        return P.set_prompt(task_key, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/prompts/{task_key}/reset")
def reset_prompt(task_key: str, _: object = Depends(current_admin)) -> dict:
    try:
        return P.reset_prompt(task_key)
    except KeyError as exc:
        raise HTTPException(status_code=404,
                            detail=f"'{task_key}' không có prompt mặc định để khôi phục") from exc