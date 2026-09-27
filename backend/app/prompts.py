"""Prompt hệ thống cho các tác vụ LLM — sửa được trong /admin.

Vì sao có bảng riêng thay vì hardcode trong code: chất lượng dịch/lồng tiếng phụ thuộc
nhiều vào prompt, và người vận hành self-host thường muốn chỉnh (giọng văn, cách xưng hô,
độ dài câu) mà không phải sửa Python. Prompt mặc định vẫn nằm trong CODE — đó là "nguồn
sự thật" để nút **Khôi phục mặc định** luôn có đích, và để bản cài mới chạy được ngay.

Quy ước biến: prompt dùng `{source}`, `{target}`, `{text}`, `{max_chars}` — khai trong
`variables` để UI hiển thị bảng gợi ý cho người sửa.
"""
from __future__ import annotations

from sqlalchemy import select

from .db import SessionLocal
from .models import Prompt

# task_key -> (prompt mặc định, mô tả, danh sách biến)
DEFAULT_PROMPTS: dict[str, dict] = {
    "translate": {
        "description": "Dịch từng câu phụ đề sang ngôn ngữ đích",
        "variables": ["source", "target", "text"],
        "content": (
            "You are a professional subtitle translator. Translate each line "
            "from {source} to {target}. Keep it short and natural — it will be "
            "spoken aloud. Reply with the translation only."
        ),
    },
    "retranslate_timing": {
        "description": "Dịch lại NGẮN HƠN để khớp thời lượng lồng tiếng",
        "variables": ["source", "target", "text", "max_chars"],
        "content": (
            "You are a professional subtitle translator working under a strict "
            "length limit. Translate this line from {source} to {target} so it "
            "can be spoken in the same amount of time as the original. Use at "
            "most {max_chars} characters, keep the meaning, drop filler words. "
            "Reply with the translation only.\n\n{text}"
        ),
    },
}


def default_prompt(task_key: str) -> str:
    d = DEFAULT_PROMPTS.get(task_key)
    return d["content"] if d else ""


def seed_prompts() -> None:
    """Tạo row cho các prompt còn thiếu. Idempotent — gọi lúc khởi động."""
    with SessionLocal() as db:
        have = {p.task_key for p in db.scalars(select(Prompt)).all()}
        for key, d in DEFAULT_PROMPTS.items():
            if key not in have:
                db.add(Prompt(task_key=key, content=d["content"],
                              description=d["description"],
                              variables=list(d["variables"]), is_default=True))
        db.commit()


def list_prompts() -> list[dict]:
    """Mọi prompt đã biết (kể cả chưa có row trong DB — trả giá trị mặc định)."""
    with SessionLocal() as db:
        rows = {p.task_key: p for p in db.scalars(select(Prompt)).all()}
    out: list[dict] = []
    keys = list(DEFAULT_PROMPTS) + [k for k in rows if k not in DEFAULT_PROMPTS]
    for key in keys:
        row = rows.get(key)
        d = DEFAULT_PROMPTS.get(key, {})
        out.append({
            "task_key": key,
            "description": row.description if row else d.get("description", ""),
            "variables": list(row.variables) if row else list(d.get("variables", [])),
            "content": row.content if row else d.get("content", ""),
            "default_content": d.get("content", ""),
            "is_default": bool(row.is_default) if row else True,
            "editable_default": key in DEFAULT_PROMPTS,
            "updated_at": row.updated_at if row else None,
        })
    return out


def get_prompt(task_key: str) -> str:
    """Prompt đang dùng: DB nếu có, ngược lại mặc định trong code.

    Bọc try/except: hàm này chạy trong worker, và DB chưa migrate KHÔNG được làm chết
    pipeline — rơi về prompt mặc định trong code là hành vi đúng.
    """
    try:
        with SessionLocal() as db:
            row = db.get(Prompt, task_key)
            if row is not None and row.content:
                return row.content
    except Exception:  # noqa: BLE001 — thiếu bảng / DB lỗi
        pass
    return default_prompt(task_key)


def set_prompt(task_key: str, content: str) -> dict:
    if not content.strip():
        raise ValueError("prompt không được để trống")
    with SessionLocal() as db:
        row = db.get(Prompt, task_key)
        d = DEFAULT_PROMPTS.get(task_key, {})
        if row is None:
            row = Prompt(task_key=task_key, description=d.get("description", ""),
                         variables=list(d.get("variables", [])))
            db.add(row)
        row.content = content
        row.is_default = (content == d.get("content"))
        db.commit()
        return {"task_key": task_key, "is_default": row.is_default}


def reset_prompt(task_key: str) -> dict:
    """Khôi phục prompt mặc định của code. Chỉ làm được với task có trong registry."""
    d = DEFAULT_PROMPTS.get(task_key)
    if d is None:
        raise KeyError(task_key)
    with SessionLocal() as db:
        row = db.get(Prompt, task_key)
        if row is None:
            row = Prompt(task_key=task_key)
            db.add(row)
        row.content = d["content"]
        row.description = d["description"]
        row.variables = list(d["variables"])
        row.is_default = True
        db.commit()
    return {"task_key": task_key, "content": d["content"], "is_default": True}


def render(task_key: str, **kwargs) -> str:
    """Prompt đã điền biến. Biến thiếu thì để nguyên chỗ trống thay vì crash job."""
    template = get_prompt(task_key)
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return template