"""Compatibility Engine — đối chiếu capability của model với System Feature Registry.

Module THUẦN (không HTTP, không DB) nên test được độc lập. Lý do tách khỏi
model_sync: sync là I/O, compat là logic thuần — logic này là ĐỊNH NGHĨA của
"model nào phù hợp với hệ thống", phải dễ đọc, dễ test, không dính network.

Bốn trạng thái (theo yêu cầu thiết kế, không dùng màu làm tín hiệu duy nhất
— badge ở UI luôn kèm text/icon):
- COMPATIBLE   — đủ điều kiện ít nhất 1 chức năng.
- PARTIAL      — biết một phần, chưa đủ bất kỳ chức năng nào.
- INCOMPATIBLE — mọi capability BẮT BUỘC đã biết đều False.
- UNKNOWN      — không đủ metadata (capability_source="none").

Điểm quan trọng về ngữ nghĩa: model KHÔNG sinh ảnh vẫn là COMPATIBLE cho hệ
thống — vì nó đủ điều kiện cho chức năng chat/dịch. "Incompatible" là hạng
dành cho model mà TẤT CẢ capability bắt buộc đã biết đều False (vd model
image-only không có text → không làm được gì trong pipeline này).
"""
from __future__ import annotations

from .capabilities import SYSTEM_FEATURES


def feature_eval(capabilities: dict, fdef: dict) -> str:
    """Đánh giá 1 feature trên 1 model → supported|partial|unsupported|unknown|skip.

    - `skip`: feature local_engine (không có model cloud nào qua registry).
    - `unsupported`: có capability bắt buộc đã biết là False ⇒ chắc chắn không làm được.
    - `supported`: ĐỦ TẤT CẢ capability bắt buộc là True.
    - `partial`: biết một phần (ít nhất một True, còn lại None).
    - `unknown`: không biết gì về capability bắt buộc nào.
    """
    if fdef.get("local_engine"):
        return "skip"
    req = fdef["required"]
    known = [capabilities.get(c) for c in req if capabilities.get(c) is not None]
    if any(v is False for v in known):
        return "unsupported"
    if req and len(known) == len(req) and all(v is True for v in known):
        return "supported"
    if known:  # biết một phần True, phần còn lại chưa xác định
        return "partial"
    return "unknown"


def compute_compatibility(capabilities: dict) -> dict:
    """Tính compatibility cho model trên TOÀN BỘ feature registry.

    Trả nguyên dict để LƯU thẳng vào cột `ai_models.compatibility` — tính lúc
    sync (thay đổi capability mới phải tính lại), đọc lúc GET thì rẻ.
    """
    effective = {k: f for k, f in SYSTEM_FEATURES.items() if not f.get("local_engine")}
    supported: list[str] = []
    partial: list[str] = []
    unsupported: list[str] = []
    unknown: list[str] = []
    for key, fdef in effective.items():
        verdict = feature_eval(capabilities, fdef)
        {"supported": supported, "partial": partial,
         "unsupported": unsupported, "unknown": unknown}.setdefault(
            verdict, []).append(key)

    any_known = any(v is not None for v in capabilities.values())
    if not any_known:
        status = "unknown"      # không đủ metadata — không suy đoán
    elif supported:
        status = "compatible"   # đủ điều kiện ≥1 chức năng (dù thiếu chức năng khác)
    elif partial:
        status = "partial"
    else:
        status = "incompatible"

    total = len(effective)
    score = round(100 * (len(supported) + 0.5 * len(partial)) / total) if total else 0

    reasons: list[str] = []
    for key in unsupported:
        missing = [c for c in effective[key]["required"] if capabilities.get(c) is False]
        if missing:
            reasons.append(f"{key}: thiếu {', '.join(missing)}")
    for key in partial:
        unclear = [c for c in effective[key]["required"] if capabilities.get(c) is None]
        if unclear:
            reasons.append(f"{key}: chưa xác nhận {', '.join(unclear)}")

    return {
        "status": status,
        "system_compatible": status == "compatible",
        "supported_features": supported,
        "partial_features": partial,
        "unsupported_features": unsupported,
        "score": score,
        "reasons": reasons[:8],
    }


def recommended_models(models: list, feature: str) -> list:
    """Xếp hạng "nên dùng" cho một feature — thuần RULE, không đoán theo tên model.

    Rule (config của hệ thống, xem mục Recommended trong capabilities/compat):
    (1) model phải enabled + provider enabled + feature nằm trong supported_features
        — caller đã lọc 2 điều kiện đầu; (2) ưu tiên capability từ metadata
    CHÍNH THỨC (`capability_source="official"`); (3) điểm compatibility cao trước;
    (4) model_id A→Z để thứ tự ổn định giữa các lần sync.
    """
    ranked = [m for m in models if feature in (m.compatibility or {}).get("supported_features", [])]
    ranked.sort(key=lambda m: (
        m.capability_source != "official",      # official trước
        -(m.compatibility or {}).get("score", 0),
        m.model_id,
    ))
    return ranked
