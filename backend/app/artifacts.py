"""Phiên bản kết quả job (GC3, C3 của lộ trình C) — append-only, KHÔNG đè.

Trước đây pipeline ghi đè file kết quả tên-cứng (`jobs/{id}/dub.mp4`) khi
"Chạy lại" — kết quả cũ biến mất. Giờ mỗi khối thành công publish output thành
phiên bản `out/result-v{N}.{ext}` + ghi row JobArtifact; `jobs.result_s3_key`
là CON TRỎ hiện hành — khôi phục chỉ đổi con trỏ.

Điểm nhất quán với resume (A1): dub đọc lại `manifest.outputs["result_key"]`
khi "Chạy lại" (dub_pipeline.py) — publish_result PHẢI ghi ngược manifest,
ngược lại lần resume sau trả key cũ rồi publish lại → tạo version rác. Subs
cùng cơ chế (`outputs["subs_key"]`).

Publish LÀ NÂNG CẤP: lỗi (đĩa đầy…) không được giết job — caller bọc try/except
và giữ key tên-cứng làm điểm khôi phục (cùng triết lý manifest.save).
"""
from __future__ import annotations

import json
import os

from sqlalchemy import func, select

from .models import Job, JobArtifact
from .pipelines.manifest import atomic_write_json, work_dir
from .storage import get_storage

KIND_RESULT = "result"
KIND_SUBS = "subtitle"


def artifact_key(job_id: str, kind: str, version: int, ext: str) -> str:
    """Key phiên bản `jobs/{id}/out/{kind}-v{N}.{ext}`.

    - Nhóm `out/` tách khỏi `work/` (file làm việc) và khỏi file tên-cứng
      legacy (dub.mp4) — không va nhau.
    - Nằm dưới `jobs/{id}/…` → `_owns_media` (main.py) và `delete_prefix`
      (storage) tự phủ — 0 dòng auth/dọn thêm.
    """
    return f"jobs/{job_id}/out/{kind}-v{version}.{ext}"


def next_version(db, job_id: str, kind: str) -> int:
    """Version kế tiếp theo (job_id, kind) — single-writer (worker -c 1) nên
    max+1 là đủ; UNIQUE constraint là rào chắn cuối."""
    current = db.scalars(
        select(func.max(JobArtifact.version)).where(
            JobArtifact.job_id == job_id, JobArtifact.kind == kind)
    ).first()
    return int(current or 0) + 1


def publish(db, job: Job, kind: str, *, source_key: str,
            filename: str | None = None) -> dict:
    """Sao chép output từ key tên-cứng sang key phiên bản + INSERT row.

    File tên-cứng NGUỒN GIỮ NGUYÊN — nó là điểm khôi phục nếu publish lỗi giữa
    đường (và delete_prefix dọn tất cả khi xóa job, không rác).
    """
    storage = get_storage()
    ext = source_key.rsplit(".", 1)[-1].lower() if "." in source_key else "bin"
    version = next_version(db, job.id, kind)
    key = artifact_key(job.id, kind, version, ext)
    storage.copy(source_key, key)
    try:
        size = len(storage.get(key))
    except Exception:  # noqa: BLE001 — size chỉ để hiển thị
        size = None
    name = filename or os.path.basename(source_key)
    db.add(JobArtifact(job_id=job.id, kind=kind, version=version, key=key,
                       filename=name, size=size))
    return {"version": version, "key": key, "filename": name, "size": size}


def _sync_manifest_outputs(job_id: str, patch: dict) -> None:
    """Ghi ngược `manifest.outputs` (JSON thuần — KHÔNG qua load_or_none vì nó
    cần fingerprint đúng, còn đây là nâng cấp best-effort)."""
    mfile = os.path.join(work_dir(job_id), "manifest.json")
    if not os.path.exists(mfile):
        return
    try:
        with open(mfile, encoding="utf-8") as f:
            data = json.load(f) or {}
        data.setdefault("outputs", {}).update(patch)
        atomic_write_json(mfile, data)
    except Exception:  # noqa: BLE001 — resume là nâng cấp, không giết job
        pass


def publish_result(db, job: Job, result_key: str) -> dict | None:
    """Publish kết quả chính + đổi con trỏ hiện hành + đồng bộ sổ tay."""
    try:
        info = publish(db, job, KIND_RESULT, source_key=result_key)
    except Exception:  # noqa: BLE001 — publish lỗi: giữ key tên-cứng
        job.params = {**(job.params or {}), "publish_error": result_key}
        return None
    job.result_s3_key = info["key"]
    _sync_manifest_outputs(job.id, {"result_key": info["key"]})
    return info


def publish_subs(db, job: Job, subs_key: str) -> dict | None:
    """Publish phụ đề song ngữ (output phụ của dub) + cập nhật extra_outputs
    (giữ shape cũ kèm version — adapt phía client không vỡ) + sổ tay."""
    try:
        info = publish(db, job, KIND_SUBS, source_key=subs_key)
    except Exception:  # noqa: BLE001 — output phụ, lỗi không giết job
        return None
    extras = [o for o in (job.params or {}).get("extra_outputs", [])
              if o.get("key") != subs_key]
    extras.append({"kind": "subtitle", "key": subs_key, "filename": info["filename"],
                   "version": info["version"]})
    job.params = {**(job.params or {}), "extra_outputs": extras}
    _sync_manifest_outputs(job.id, {"subs_key": subs_key})
    return info


def current_flags(db, job: Job) -> list[dict]:
    """List artifact + cờ `current` (đang là kết quả hiện hành hay không) —
    UI dùng để tô đậm dòng đang được tải."""
    cur_result = job.result_s3_key
    cur_subs = next((o.get("key") for o in (job.params or {})
                     .get("extra_outputs", []) if o.get("kind") == "subtitle"), None)
    rows = db.scalars(
        select(JobArtifact).where(JobArtifact.job_id == job.id)
        .order_by(JobArtifact.kind, JobArtifact.version)
    ).all()
    return [{
        "version": a.version, "kind": a.kind, "key": a.key,
        "filename": a.filename, "size": a.size, "created_at": a.created_at,
        "current": (a.key == cur_result if a.kind == KIND_RESULT
                    else a.key == cur_subs),
    } for a in rows]
