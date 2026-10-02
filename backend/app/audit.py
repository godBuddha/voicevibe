"""Nhật ký hành động (audit log) — best-effort, không bao giờ làm gãy request.

Nguyên tắc: `log_action` mở SessionLocal RIÊNG (pattern `_record_stt_stats` của
tasks.py — session của request có thể đã đóng hoặc đang trong giao dịch khác),
commit xong đóng ngay, và bọc toàn bộ trong try/except. Một lỗi ghi audit
(DB khoá, bảng chưa migrate, DB sập) KHÔNG ĐƯỢC phá hành động đang diễn ra —
thiếu một dòng nhật ký vẫn tốt hơn hành động thất bại.

KHÔNG log endpoint đọc (GET) — audit là nhật ký HÀNH ĐỘNG, không phải access log;
log mọi GET sẽ phình bảng và che mất tín hiệu thật.
"""
from __future__ import annotations

from .db import SessionLocal
from .models import AuditLog

# Registry hành động — dùng cho test + dropdown lọc của UI (Quan sát → Nhật ký).
# Nhóm theo domain: auth.<tác vụ> | me.<tác vụ> | user.<tác vụ> | provider.<tác vụ>
# | stage.<tác vụ> | model.<tác vụ> | setting.<tác vụ> | key.<tác vụ>
# | prompt.<tác vụ> | job.<tác vụ> | config.<tác vụ>
ACTIONS: tuple[str, ...] = (
    "auth.login",
    "auth.login_failed",
    "auth.logout",
    "auth.setup",
    "auth.signup",
    "me.password_change",
    "me.name_change",
    "me.session_revoke",
    "user.create",
    "user.reset_password",
    "user.deactivate",
    "user.activate",
    "provider.create",
    "provider.update",
    "provider.delete",
    "provider.sync",
    "stage.set",
    "stage.clear",
    "model.toggle",
    "setting.set",
    "setting.delete",
    "key.create",
    "key.revoke",
    "prompt.update",
    "prompt.reset",
    "job.cancel",
    "job.retry",
    "job.delete",
    "config.import",
)


def log_action(action: str, *, user_id: str | None = None,
               target: str | None = None, detail: str | None = None,
               ip: str | None = None) -> None:
    """Ghi một dòng audit. KHÔNG BAO GIỜ raise — thấy lỗi thì nuốt im lặng.

    `target` thường là "đối tượng bị tác động" (email user, tên provider, key
    setting, id job); `detail` là bối cảnh ngắn (vd `enabled=true`). Giá trị cut
    đúng độ dài cột để không lỗi DB khi chuỗi dài hơn dự kiến.
    """
    try:
        with SessionLocal() as db:
            db.add(AuditLog(
                action=action[:64],
                user_id=user_id[:12] if user_id else None,
                target=target[:128] if target else None,
                detail=detail[:500] if detail else None,
                ip=ip[:64] if ip else None,
            ))
            db.commit()
    except Exception:
        # Nhật ký không được phá hành động đang ghi nó — kể cả lỗi schema cũ
        # (bảng chưa tồn tại trên DB chưa restart worker).
        pass
