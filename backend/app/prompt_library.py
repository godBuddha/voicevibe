"""Thư viện Prompt — prompt cá nhân theo user (khác prompt hệ thống của bảng prompts).

Mỗi user đăng nhập được tạo/sửa/xoá prompt của riêng mình; khi tạo job Dịch văn bản
có thể chọn 1 prompt để thay system prompt. Quy tắc:

1. **Riêng tư theo user**: mọi query lọc `user_id` của chủ; đụng prompt của người
   khác → **404** (không 403 — không lộ sự tồn tại, pattern voice ownership).
2. **Versioning nhẹ**: mỗi lần LƯU, nội dung CŨ được chụp vào cột `history`
   (tối đa 20 bản, mới nhất ở đầu). Khôi phục = snapshot bản hiện tại thành
   version mới — lịch sử chỉ đi tới, không xoá.
3. **Biến do server tự dò** (`scan_variables` của app.prompts) — client không
   khai báo. Chỉ thay biến đã truyền khi render (`render_template`): biến thiếu
   giữ nguyên `{tên}` thay vì làm chết cả prompt.
4. API key thật không liên quan ở đây — prompt là nội dung người dùng tự tạo.

Phân quyền: endpoint user dùng `Depends(auth)` (mọi user đăng nhập); admin có
MỘT endpoint read-only (`/v1/admin/prompt-library`) xem thư viện của user nào
đang có gì — sửa/xoá HỘ user là scope creep, không làm.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import auth, current_admin
from .db import get_db
from .models import PromptLibrary, User
from .prompts import scan_variables

router = APIRouter(tags=["prompt-library"])

_NAME_MAX = 120
_CONTENT_MAX = 20_000
_TAGS_MAX = 8
_TAG_LEN = 24
_HISTORY_MAX = 20
_DESC_MAX = 255


# ------------------------------------------------------------------ helpers
def _norm_tags(raw: list[str] | None) -> list[str]:
    """Chuẩn hoá tags: strip, bỏ rỗng, dedupe giữ thứ tự. Vượt 8 tag → ValueError
    (endpoint quy thành 422 — chấm dứt rõ ràng tốt hơn im lặng cắt bớt)."""
    out: list[str] = []
    for t in raw or []:
        t = (t or "").strip()[:_TAG_LEN]
        if t and t not in out:
            out.append(t)
    if len(out) > _TAGS_MAX:
        raise ValueError(f"tối đa {_TAGS_MAX} tag")
    return out


def _next_version(history: list) -> int:
    return max((e.get("v", 0) for e in history), default=0) + 1


def _snapshot_old(row: PromptLibrary, note: str | None, user_id: str) -> None:
    """Chụp nội dung HIỆN TẠI vào history (gọi trước khi ghi nội dung mới).
    GÁN OBJECT MỚI — mutate list tại chỗ không flush (xem docstring model)."""
    entry = {
        "v": _next_version(row.history or []),
        "content": row.content,
        "note": (note or "").strip()[:120] or None,
        "updated_at": row.updated_at or 0,
        "by": user_id,
    }
    new_hist = [entry, *(row.history or [])]
    if len(new_hist) > _HISTORY_MAX:
        new_hist = new_hist[:_HISTORY_MAX]
    row.history = new_hist


def _row_out(row: PromptLibrary, *, full: bool = True) -> dict:
    """Shape trả ra API. List dùng full=False: content chỉ còn preview, history
    chỉ còn đếm — list hàng nghìn prompt không phình payload."""
    hist = row.history or []
    # version hiện tại = v của bản CŨ NHẤT bị chụp + 1 ... đơn giản hơn: nếu
    # chưa từng lưu (history rỗng) là v1; đã lưu thì v tiếp theo sẽ là max+1,
    # nên "đang ở" = max+1 trừ đi 1 = max. Cách chắc chắn nhất: max+1 nếu
    # history có dữ liệu (bản hiện tại là kế tiếp của bản cao nhất bị chụp).
    version = max((e.get("v", 0) for e in hist), default=0) + 1
    base = {
        "id": row.id, "name": row.name, "description": row.description,
        "tags": list(row.tags or []), "variables": list(row.variables or []),
        "version": version, "history_count": len(hist),
        "created_at": row.created_at, "updated_at": row.updated_at,
    }
    if full:
        return {**base, "content": row.content, "history": hist}
    preview = row.content[:100] + ("…" if len(row.content) > 100 else "")
    return {**base, "content_preview": preview}


def _get_own(db: Session, prompt_id: str, user: User) -> PromptLibrary:
    """Lấy prompt của CHÍNH user này — None/khác chủ → 404 (không lộ tồn tại)."""
    row = db.get(PromptLibrary, prompt_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="không tìm thấy prompt")
    return row


# ------------------------------------------------------------------- schemas
class PromptIn(BaseModel):
    name: str
    content: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class PromptPatch(BaseModel):
    name: str | None = None
    content: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    note: str | None = None   # ghi chú phiên bản (hiện ở lịch sử)


class RestoreIn(BaseModel):
    version: int


# ------------------------------------------------------------------- endpoints
@router.get("/v1/prompts")
def list_prompts(user: User = Depends(auth), db: Session = Depends(get_db),
                 q: str | None = None, tag: str | None = None,
                 limit: int = 50, offset: int = 0) -> dict:
    if limit < 1 or limit > 200:
        limit = 50
    if offset < 0:
        offset = 0
    rows = db.scalars(select(PromptLibrary)
                      .where(PromptLibrary.user_id == user.id)
                      .order_by(PromptLibrary.updated_at.desc())).all()
    if q:
        needle = q.lower()
        rows = [r for r in rows
                if needle in r.name.lower() or needle in (r.description or "").lower()]
    if tag:
        rows = [r for r in rows if tag in (r.tags or [])]
    total = len(rows)
    return {"prompts": [_row_out(r, full=False) for r in rows[offset:offset + limit]],
            "total": total}


@router.post("/v1/prompts", status_code=201)
def create_prompt(body: PromptIn, user: User = Depends(auth),
                  db: Session = Depends(get_db)) -> dict:
    try:
        return _create(db, user, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _create(db: Session, user: User, body: PromptIn) -> dict:
    name = body.name.strip()
    content = body.content.strip()
    if not name or len(name) > _NAME_MAX:
        raise HTTPException(status_code=422,
                            detail=f"tên prompt phải 1..{_NAME_MAX} ký tự")
    if not content or len(content) > _CONTENT_MAX:
        raise HTTPException(status_code=422,
                            detail=f"nội dung prompt phải 1..{_CONTENT_MAX} ký tự")
    desc = (body.description or "").strip()[:_DESC_MAX]
    row = PromptLibrary(user_id=user.id, name=name, content=content, description=desc,
                        variables=scan_variables(content), tags=_norm_tags(body.tags),
                        history=[])
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_out(row)


@router.get("/v1/prompts/{prompt_id}")
def get_prompt(prompt_id: str, user: User = Depends(auth),
               db: Session = Depends(get_db)) -> dict:
    return _row_out(_get_own(db, prompt_id, user))


@router.put("/v1/prompts/{prompt_id}")
def update_prompt(prompt_id: str, body: PromptPatch, user: User = Depends(auth),
                  db: Session = Depends(get_db)) -> dict:
    row = _get_own(db, prompt_id, user)
    try:
        _update(db, row, body, user)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _row_out(row)


def _update(db: Session, row: PromptLibrary, body: PromptPatch, user: User) -> None:
    if body.name is not None:
        name = body.name.strip()
        if not name or len(name) > _NAME_MAX:
            raise HTTPException(status_code=422,
                                detail=f"tên prompt phải 1..{_NAME_MAX} ký tự")
        row.name = name
    if body.description is not None:
        row.description = body.description.strip()[:_DESC_MAX]
    if body.tags is not None:
        row.tags = _norm_tags(body.tags)   # gán object mới qua _norm_tags output
    if body.content is not None:
        content = body.content.strip()
        if not content or len(content) > _CONTENT_MAX:
            raise HTTPException(status_code=422,
                                detail=f"nội dung prompt phải 1..{_CONTENT_MAX} ký tự")
        if content != row.content:
            _snapshot_old(row, body.note, user.id)   # TRƯỚC khi ghi nội dung mới
            row.content = content
            row.variables = scan_variables(content)
    db.commit()


@router.post("/v1/prompts/{prompt_id}/restore")
def restore_prompt(prompt_id: str, body: RestoreIn, user: User = Depends(auth),
                   db: Session = Depends(get_db)) -> dict:
    """Khôi phục version: snapshot bản HIỆN TẠI thành version mới rồi gán lại
    nội dung bản cũ — lịch sử chỉ đi tới, không mất bản nào."""
    row = _get_own(db, prompt_id, user)
    entry = next((e for e in (row.history or []) if e.get("v") == body.version), None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"version {body.version} không tồn tại")
    _snapshot_old(row, f"khôi phục v{body.version}", user.id)
    row.content = entry["content"]
    row.variables = scan_variables(entry["content"])
    db.commit()
    db.refresh(row)
    return _row_out(row)


@router.delete("/v1/prompts/{prompt_id}")
def delete_prompt(prompt_id: str, user: User = Depends(auth),
                  db: Session = Depends(get_db)) -> dict:
    row = _get_own(db, prompt_id, user)
    db.delete(row)
    db.commit()
    return {"id": prompt_id, "deleted": True}


# -------------------------------------------------------- worker-safe helper
def resolve_prompt_override(prompt_id: str, owner_user_id: str) -> str | None:
    """Prompt cá nhân cho job Dịch — chạy trong worker (session riêng), DB lỗi
    KHÔNG được làm chết pipeline: trả None → job dùng prompt hệ thống như cũ.

    WHERE có `user_id`: chặn cả trường hợp prompt bị XOÁ/đổi chủ giữa lúc tạo
    job và lúc worker chạy — prompt của người khác không bao giờ được dán vào job.
    """
    try:
        from .db import SessionLocal
        with SessionLocal() as db:
            row = db.get(PromptLibrary, prompt_id)
            if row is None or row.user_id != owner_user_id or not (row.content or "").strip():
                return None
            return row.content
    except Exception:  # noqa: BLE001 — DB chưa migrate / lỗi → rơi về mặc định
        return None


# ---------------------------------------------------------------- admin (read-only)
@router.get("/v1/admin/prompt-library")
def admin_list(user: User = Depends(current_admin), db: Session = Depends(get_db),
               q: str | None = None, user_id: str | None = None,
               limit: int = 50, offset: int = 0) -> dict:
    """Admin xem thư viện của mọi user (read-only — sửa/xoá hộ user là không làm)."""
    if limit < 1 or limit > 200:
        limit = 50
    rows = db.scalars(select(PromptLibrary).order_by(PromptLibrary.updated_at.desc())).all()
    if user_id:
        rows = [r for r in rows if r.user_id == user_id]
    if q:
        needle = q.lower()
        rows = [r for r in rows if needle in r.name.lower()]
    users = {u.id: u.email for u in db.scalars(select(User)).all()}
    total = len(rows)
    items = []
    for r in rows[offset:offset + limit]:
        items.append({**_row_out(r, full=False),
                      "user_id": r.user_id,
                      "user_email": users.get(r.user_id),
                      "content_length": len(r.content or "")})
    return {"items": items, "total": total}
