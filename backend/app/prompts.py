"""Prompt hệ thống cho các tác vụ LLM — sửa được trong /admin.

Vì sao có bảng riêng thay vì hardcode trong code: chất lượng dịch/lồng tiếng phụ thuộc
nhiều vào prompt, và người vận hành self-host thường muốn chỉnh (giọng văn, cách xưng hô,
độ dài câu) mà không phải sửa Python. Prompt mặc định vẫn nằm trong CODE — đó là "nguồn
sự thật" để nút **Khôi phục mặc định** luôn có đích, và để bản cài mới chạy được ngay.

Quy ước biến: prompt dùng `{source}`, `{target}`, `{text}`, `{max_chars}` — khai trong
`variables` để UI hiển thị bảng gợi ý cho người sửa.
"""
from __future__ import annotations

import re

from sqlalchemy import select

from .db import SessionLocal
from .models import Prompt

# `{tên_biến}` — chữ, số, gạch dưới. Không hỗ trợ format spec (`{x:>5}`) một cách
# có chủ đích: prompt là văn bản cho LLM, không phải template trình bày.
_PLACEHOLDER = re.compile(r"\{(\w+)\}")

# task_key -> (prompt mặc định, mô tả, danh sách biến)
DEFAULT_PROMPTS: dict[str, dict] = {
    "translate": {
        "description": "Dịch từng câu phụ đề sang ngôn ngữ đích",
        # `text` KHÔNG có ở đây: prompt này là system prompt, còn nội dung cần dịch
        # đi ở message của user (xem CloudChatTranslator). Khai `text` sẽ khiến
        # người sửa prompt tưởng dùng được `{text}` rồi thấy nó nằm trần trong prompt.
        "variables": ["source", "target"],
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
    "translate_batch": {
        "description": (
            "Dịch LOẠT nhiều câu trong MỘT lượt gọi LLM (Lồng tiếng, Phụ đề "
            "song ngữ) — đây là message HỆ THỐNG; danh sách câu + yêu cầu JSON "
            "do hệ thống dựng ở message người dùng, không đưa vào đây."
        ),
        "variables": ["source", "target", "batch_size", "context_count"],
        "content": (
            "Bạn là một biên dịch viên phụ đề chuyên nghiệp. Dịch {batch_size} câu "
            "từ {source} sang {target} để LỒNG TIẾNG — bản dịch sẽ được đọc to, nên "
            "phải NGẮN GỌN, tự nhiên, đúng nhịp nói. Giữ đúng tên riêng, số và thuật "
            "ngữ. KHÔNG dịch phần ngữ cảnh, KHÔNG thêm lời giải thích, KHÔNG đổi số "
            "lượng câu. Chỉ trả về JSON đúng cấu trúc được yêu cầu."
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


def scan_variables(template: str) -> list[str]:
    """Danh sách {token} unique trong template, THEO THỨ TỪ xuất hiện.

    Dùng chung: `render()` nội bộ và Thư viện Prompt (server re-scan biến khi
    lưu — client không được khai báo biến thay server).
    """
    seen: dict[str, None] = {}
    for m in _PLACEHOLDER.finditer(template or ""):
        seen.setdefault(m.group(1), None)
    return list(seen)


def render_template(template: str, **kwargs) -> str:
    """Điền biến vào template THÔ — chỉ thay biến ĐÃ truyền, giữ nguyên `{tên}` của
    biến thiếu. Thân của `render()` (tách ra để Thư viện Prompt dùng cùng quy tắc
    khi render prompt cá nhân — không lặp regex ở module khác).
    """
    return _PLACEHOLDER.sub(
        lambda m: str(kwargs[m.group(1)]) if m.group(1) in kwargs else m.group(0),
        template or "")


def render(task_key: str, **kwargs) -> str:
    """Prompt đã điền biến: chỉ thay biến ĐÃ truyền, giữ nguyên `{tên}` của biến thiếu.

    KHÔNG dùng `str.format`. Nó ném `KeyError` khi thiếu *bất kỳ* biến nào, và bản
    trước bắt lỗi đó rồi trả về NGUYÊN template — nên `CloudChatTranslator` (chỉ
    truyền `source`/`target` vì phần text nằm ở message của user) đã gửi cho model
    đúng chuỗi "Translate each line from {source} to {target}": mất hẳn thông tin
    cặp ngôn ngữ, mà không có gì trong UI hay log báo sai.

    Thay bằng một lượt regex (không lặp lại) để giá trị vừa thay không bị thay
    tiếp — ví dụ bản dịch có chứa `{source}`.
    """
    return render_template(get_prompt(task_key), **kwargs)