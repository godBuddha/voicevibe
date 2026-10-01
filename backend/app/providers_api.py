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
from .audit import log_action
from .auth import current_admin
from .db import get_db
from .models import (
    AiModel,
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


def _provider_stats(db: Session) -> dict[str, dict]:
    """Thống kê registry theo provider (1 query duy nhất — không N+1).

    Trả {provider_id: {models_count, last_synced_at, breakdown{4 trạng thái}}}
    cho `list_providers`. Đếm bằng Python trên tập đã SELECT: self-host 1 node,
    vài nghìn row là quá nhỏ so với chi phí GROUP BY JSON cột phức tạp.
    """
    stats: dict[str, dict] = {}
    for m in db.scalars(select(AiModel)).all():
        s = stats.setdefault(m.provider_id, {
            "models_count": 0, "last_synced_at": None,
            "breakdown": {"compatible": 0, "partial": 0, "unknown": 0, "incompatible": 0},
        })
        s["models_count"] += 1
        if m.last_synced_at and m.last_synced_at > (s["last_synced_at"] or 0):
            s["last_synced_at"] = m.last_synced_at
        status = (m.compatibility or {}).get("status", "unknown")
        if status in s["breakdown"]:
            s["breakdown"][status] += 1
    return stats


def _model_out(m: AiModel, provider: AiProvider | None = None,
               full_description: bool = False) -> dict:
    """Bản ghi model cho API. `full_description=True` ở endpoint chi tiết —
    list chỉ trả 400 ký tự đầu để trang không phình khi có hàng nghìn model."""
    desc = m.description or ""
    if not full_description and len(desc) > 400:
        desc = desc[:400] + "…"
    return {
        "id": m.id, "provider_id": m.provider_id,
        "provider_name": provider.name if provider else None,
        "provider_enabled": provider.enabled if provider else True,
        "model_id": m.model_id, "display_name": m.display_name,
        "description": desc or None, "org": m.org, "enabled": m.enabled,
        "capabilities": m.capabilities or {},
        "capability_source": m.capability_source,
        "context_window": m.context_window,
        "input_token_limit": m.input_token_limit,
        "output_token_limit": m.output_token_limit,
        "pricing": m.pricing, "metadata": m.metadata_ or {},
        "compatibility": m.compatibility or {},
        "last_synced_at": m.last_synced_at,
        "created_at": m.created_at, "updated_at": m.updated_at,
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


def _out_full(db: Session, p: AiProvider) -> dict:
    """`_out` + thống kê registry (dùng cho POST/PATCH — response đồng nhất shape
    với list, UI cập nhật state không phải tự bồi thêm field)."""
    s = _provider_stats(db).get(p.id)
    d = _out(p)
    d["models_count"] = s["models_count"] if s else 0
    d["last_synced_at"] = s["last_synced_at"] if s else None
    d["breakdown"] = (s or {"breakdown": {
        "compatible": 0, "partial": 0, "unknown": 0, "incompatible": 0}})["breakdown"]
    return d


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
    stats = _provider_stats(db)
    out = []
    for p in rows:
        d = _out(p)
        s = stats.get(p.id)
        d["models_count"] = s["models_count"] if s else 0
        d["last_synced_at"] = s["last_synced_at"] if s else None
        d["breakdown"] = (s or {"breakdown": {
            "compatible": 0, "partial": 0, "unknown": 0, "incompatible": 0}})["breakdown"]
        out.append(d)
    return {"providers": out}


@router.post("/providers", status_code=201)
def create_provider(body: ProviderIn, admin: object = Depends(current_admin),
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
    log_action("provider.create", user_id=getattr(admin, "id", None), target=p.name,
               detail=f"kind={p.kind} base_url={p.base_url}")
    return _out_full(db, p)


@router.patch("/providers/{provider_id}")
def patch_provider(provider_id: str, body: ProviderPatch,
                   admin: object = Depends(current_admin),
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
    log_action("provider.update", user_id=getattr(admin, "id", None), target=p.name)
    return _out_full(db, p)


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: str, admin: object = Depends(current_admin),
                    db: Session = Depends(get_db)) -> dict:
    p = _get(db, provider_id)
    # Gỡ liên kết công đoạn trước khi xoá (FK có thể là NULL) để không còn trỏ vào hư không.
    for sm in db.scalars(select(StageModel).where(StageModel.provider_id == p.id)).all():
        db.delete(sm)
    # Registry model của provider cũng xoá theo (model là dữ liệu phái sinh từ
    # provider — provider biến mất thì catalog của nó không còn nghĩa).
    for m in db.scalars(select(AiModel).where(AiModel.provider_id == p.id)).all():
        db.delete(m)
    name = p.name
    db.delete(p)
    db.commit()
    log_action("provider.delete", user_id=getattr(admin, "id", None), target=name)
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
def set_stage(stage: str, body: StageIn, admin: object = Depends(current_admin),
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
    log_action("stage.set", user_id=getattr(admin, "id", None),
               target=f"{stage}#{row.order}", detail=row.model or "(mặc định)")
    return {"stage": stage, "provider_id": row.provider_id, "model": row.model,
            "order": row.order}


@router.delete("/stages/{stage}")
def clear_stage(stage: str, order: int = 0, admin: object = Depends(current_admin),
                db: Session = Depends(get_db)) -> dict:
    row = db.scalar(select(StageModel).where(StageModel.stage == stage,
                                             StageModel.order == order))
    if row is not None:
        db.delete(row)
        db.commit()
        log_action("stage.clear", user_id=getattr(admin, "id", None),
                   target=f"{stage}#{order}")
    return {"stage": stage, "cleared": row is not None}


def stage_chain(stage: str, db: Session) -> list[dict]:
    """Chuỗi fallback của một công đoạn, đã giải mã key — dùng cho pipeline.

    Ba lọc mới (Model Registry): (1) row `model` rỗng bị bỏ — UI từng cho lưu
    "(mặc định)" dưới dạng chuỗi rỗng và runtime gọi API với `model: ""` → 400
    (lỗi đã gặp thật); (2) model có trong registry mà `enabled=False` bị bỏ —
    Enable/Disable phải có hiệu lực RUNTIME, không chỉ đổi trạng thái trên UI;
    (3) model KHÔNG có trong registry vẫn giữ — cấu hình tay cũ hoạt động như
    trước (không có trong catalog thì không biết để chặn).
    """
    rows = db.scalars(select(StageModel).where(StageModel.stage == stage)
                      .order_by(StageModel.order)).all()
    out: list[dict] = []
    for r in rows:
        if not r.provider_id:
            continue
        p = db.get(AiProvider, r.provider_id)
        if p is None or not p.enabled:
            continue
        model = (r.model or "").strip()
        if not model:
            continue
        reg = db.scalar(select(AiModel).where(
            AiModel.provider_id == p.id, AiModel.model_id == model))
        if reg is not None and not reg.enabled:
            continue
        out.append({"kind": p.kind, "base_url": _norm_base(p.base_url),
                    "api_key": _decrypt(p.api_key_enc) or "",
                    "model": model, "params": r.params or {},
                    "provider_id": p.id})
    return out


def stage_entry(stage: str, db: Session) -> dict | None:
    """Entry CLOUD đầu tiên của công đoạn — dùng cho STT/TTS runtime.

    Chỉ nhận kind=openai: Ollama không phục vụ /audio/* (không có STT/TTS HTTP
    chuẩn), và audio pipeline nói chuẩn OpenAI. Không có entry hợp lệ → None
    (pipeline rơi về engine local)."""
    for e in stage_chain(stage, db):
        if e["kind"] == PROVIDER_OPENAI and e["model"]:
            return e
    return None


# ------------------------------------------------------- Model Registry (sync/list)
@router.post("/providers/{provider_id}/sync")
def sync_models(provider_id: str, admin: object = Depends(current_admin),
                db: Session = Depends(get_db)) -> dict:
    """Đồng bộ model registry: fetch → chuẩn hoá → capability → upsert/xoá.

    Lỗi fetch (mạng/JSON/HTTP) → 502 và KHÔNG ghi gì vào DB — bấm lại được,
    không bao giờ rơi vào trạng thái nửa vời. Lỗi từng model (Ollama /api/show)
    không làm chết sync — nằm trong `errors` của kết quả."""
    from .model_sync import sync_provider, SyncError
    p = _get(db, provider_id)
    try:
        result = sync_provider(db, p)
    except SyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"không lấy được danh sách model: {exc.__class__.__name__}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="phản hồi không phải JSON hợp lệ") from exc
    log_action("provider.sync", user_id=getattr(admin, "id", None), target=p.name,
               detail=f"added={result.get('added')} updated={result.get('updated')} "
                      f"removed={result.get('removed')}")
    return result


def _filter_models(db: Session, provider: dict | None = None, **_ignored) -> list[AiModel]:
    """Tất cả model của các provider (kèm provider lookup cho _model_out).

    Filter JSON bằng SQL khác nhau giữa SQLite/Postgres — repo này chạy cả hai
    dialect, nên lọc python-side sau MỘT SELECT. Self-host 1 node, vài nghìn
    row: toàn bộ phép lọc + sort < 5ms — không phải tối ưu sớm."""
    providers = {p.id: p for p in db.scalars(select(AiProvider)).all()}
    rows = db.scalars(select(AiModel).order_by(AiModel.model_id)).all()
    return rows, providers


@router.get("/models")
def list_models(_: object = Depends(current_admin),
                db: Session = Depends(get_db),
                limit: int = 50, offset: int = 0,
                q: str | None = None,
                provider_id: str | None = None,
                org: str | None = None,
                capability: str | None = None,
                compatibility: str | None = None,
                enabled: str | None = None,
                feature: str | None = None) -> dict:
    """Model Registry có filter + phân trang. `breakdown` tính trên TOÀN BỘ
    registry (không theo filter) — chip đếm ở UI phải ổn định khi đang lọc."""
    from .capabilities import CAPABILITIES, SYSTEM_FEATURES
    from .compat import feature_eval
    if limit < 1 or limit > 200:
        limit = 50
    if offset < 0:
        offset = 0
    rows, providers = _filter_models(db)
    if provider_id:
        rows = [m for m in rows if m.provider_id == provider_id]
    if org:
        rows = [m for m in rows if (m.org or "").lower() == org.lower()]
    if capability:
        if capability not in CAPABILITIES:
            raise HTTPException(status_code=422, detail=f"capability phải thuộc {list(CAPABILITIES)}")
        rows = [m for m in rows if (m.capabilities or {}).get(capability) is True]
    if compatibility:
        if compatibility not in {"compatible", "partial", "unknown", "incompatible"}:
            raise HTTPException(status_code=422, detail="compatibility không hợp lệ")
        rows = [m for m in rows
                if (m.compatibility or {}).get("status") == compatibility]
    if enabled is not None:
        want = enabled.lower() in {"1", "true", "yes"}
        rows = [m for m in rows if bool(m.enabled) == want]
    if q:
        needle = q.lower()
        rows = [m for m in rows
                if needle in (m.model_id or "").lower()
                or needle in (m.display_name or "").lower()]
    if feature:
        fdef = SYSTEM_FEATURES.get(feature)
        if fdef is None:
            raise HTTPException(status_code=422, detail=f"feature '{feature}' không tồn tại")
        rows = [m for m in rows
                if feature_eval(m.capabilities or {}, fdef) == "supported"]
    total = len(rows)
    page = rows[offset:offset + limit]
    breakdown = {"compatible": 0, "partial": 0, "unknown": 0, "incompatible": 0}
    for m in db.scalars(select(AiModel)).all():
        status = (m.compatibility or {}).get("status", "unknown")
        if status in breakdown:
            breakdown[status] += 1
    return {
        "items": [_model_out(m, providers.get(m.provider_id)) for m in page],
        "total": total, "limit": limit, "offset": offset,
        "breakdown": breakdown,
        "providers": {pid: pr.name for pid, pr in providers.items()},
    }


@router.get("/models/{model_id}")
def get_model(model_id: str, _: object = Depends(current_admin),
              db: Session = Depends(get_db)) -> dict:
    m = db.get(AiModel, model_id)
    if m is None:
        raise HTTPException(status_code=404, detail="không tìm thấy model")
    return _model_out(m, db.get(AiProvider, m.provider_id), full_description=True)


class ModelPatch(BaseModel):
    enabled: bool | None = None


@router.patch("/models/{model_id}")
def patch_model(model_id: str, body: ModelPatch, admin: object = Depends(current_admin),
                db: Session = Depends(get_db)) -> dict:
    """Bật/tắt model — trạng thái RIÊNG của registry, sync không đụng (xem
    sync_provider). Disabled model: không hiện trong selector, không được gán
    stage, bị stage_chain loại bỏ lúc runtime."""
    m = db.get(AiModel, model_id)
    if m is None:
        raise HTTPException(status_code=404, detail="không tìm thấy model")
    if body.enabled is not None:
        m.enabled = body.enabled
    db.commit()
    db.refresh(m)
    log_action("model.toggle", user_id=getattr(admin, "id", None),
               target=m.model_id[:128], detail=f"enabled={m.enabled}")
    return _model_out(m, db.get(AiProvider, m.provider_id), full_description=True)


@router.get("/features")
def list_features(_: object = Depends(current_admin),
                  db: Session = Depends(get_db)) -> dict:
    """Feature registry + số model tương thích từng feature — dùng cho tab
    Features và model selector. Đếm python-side trên 1 SELECT (xem _filter_models)."""
    from .capabilities import SYSTEM_FEATURES, feature_stage
    from .compat import feature_eval
    rows = db.scalars(select(AiModel)).all()
    providers = {p.id: p for p in db.scalars(select(AiProvider)).all()}
    features = []
    for key, fdef in SYSTEM_FEATURES.items():
        compatible = partial = 0
        for m in rows:
            pr = providers.get(m.provider_id)
            if pr is None or not pr.enabled or not m.enabled:
                continue
            verdict = feature_eval(m.capabilities or {}, fdef)
            if verdict == "supported":
                compatible += 1
            elif verdict == "partial":
                partial += 1
        features.append({
            "key": key, "label": fdef["label"], "stage": feature_stage(key),
            "required": fdef["required"], "optional": fdef.get("optional", []),
            "local_engine": bool(fdef.get("local_engine")),
            "models_compatible": compatible, "models_partial": partial,
        })
    return {"features": features}


@router.get("/features/{feature_key}/models")
def feature_models(feature_key: str, _: object = Depends(current_admin),
                   db: Session = Depends(get_db),
                   limit: int = 50, offset: int = 0,
                   include_disabled: str | None = None) -> dict:
    """Tìm model tương thích cho một CHỨC NĂNG (yêu cầu: feature có thể tìm
    model). Mặc định chỉ model enabled của provider enabled — disabled chỉ hiện
    khi `include_disabled=1`."""
    from .capabilities import SYSTEM_FEATURES, STAGE_FEATURES
    from .compat import feature_eval
    fdef = SYSTEM_FEATURES.get(feature_key)
    if fdef is None:
        raise HTTPException(status_code=404, detail=f"feature '{feature_key}' không tồn tại")
    if limit < 1 or limit > 200:
        limit = 50
    rows, providers = _filter_models(db)
    verdicts = {}
    out = []
    for m in rows:
        pr = providers.get(m.provider_id)
        if pr is None:
            continue
        verdict = feature_eval(m.capabilities or {}, fdef)
        verdicts[m.id] = verdict
        include = include_disabled in {"1", "true", "yes"}
        if not include:
            if not m.enabled or not pr.enabled:
                continue
        if verdict in {"supported", "partial"}:
            out.append(m)
    # supported trước, partial sau; trong cùng nhóm: official trước, score cao trước
    def _rank(m):
        v = verdicts[m.id]
        comp = m.compatibility or {}
        return (0 if v == "supported" else 1,
                0 if m.capability_source == "official" else 1,
                -comp.get("score", 0), m.model_id)
    out.sort(key=_rank)
    total = len(out)
    page = out[offset:offset + limit]
    return {
        "feature": feature_key, "total": total, "limit": limit, "offset": offset,
        "items": [{"verdict": verdicts[m.id],
                   **_model_out(m, providers.get(m.provider_id))} for m in page],
    }


# ------------------------------------------------------------------------ prompt
class PromptIn(BaseModel):
    content: str


@router.get("/prompts")
def list_prompts(_: object = Depends(current_admin)) -> dict:
    return {"prompts": P.list_prompts()}


@router.put("/prompts/{task_key}")
def put_prompt(task_key: str, body: PromptIn, admin: object = Depends(current_admin)) -> dict:
    try:
        out = P.set_prompt(task_key, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    log_action("prompt.update", user_id=getattr(admin, "id", None), target=task_key)
    return out


@router.post("/prompts/{task_key}/reset")
def reset_prompt(task_key: str, admin: object = Depends(current_admin)) -> dict:
    try:
        out = P.reset_prompt(task_key)
    except KeyError as exc:
        raise HTTPException(status_code=404,
                            detail=f"'{task_key}' không có prompt mặc định để khôi phục") from exc
    log_action("prompt.reset", user_id=getattr(admin, "id", None), target=task_key)
    return out