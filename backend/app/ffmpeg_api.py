"""GD1 — API "Dịch thành lệnh" cho Bàn điều khiển FFmpeg (router riêng).

Vì sao router riêng (không nhét main.py): preview là MỘT endpoint LLM call
đắt (đắng tiền/giây), tách file cho test monkeypatch gọn và không phình
main.py (đã 1500+ dòng). Router này KHÔNG chạy lệnh — chỉ DỊCH và VALIDATE;
"Chạy lệnh này" tạo job type=ffmpeg qua /v1/jobs như mọi job khác (same gate
_validate_job_in). Preview KHÔNG audit (hành động đọc-like; audit bắt đầu ở
khi có job).

Model LLM: `summary.build_chat()` tái dùng NGUYÊN VẸN — stage "summarize"
trong Model Hub → settings translate.* → None. Không thêm stage mới cho
ffmpeg (cắt theo kế hoạch GD1; docstring này là ghi chú phép tái dụng).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import auth
from .db import get_db
from .models import MediaObject, User
from .pipelines.ffmpeg_cmd import INPUT_PREFIX, build_prompt, command_to_argv
from .ratelimit import check_rate

router = APIRouter()

# Đuôi file nguồn quen thuộc (media upload / link có đuôi). Link không có đuôi
# → "mp4" (mặc định hợp lý; khi job chạy worker REWRITE ext theo file thật).
_KNOWN_EXTS = ("mp4", "mkv", "webm", "mov", "m4a", "mp3", "wav", "aac",
               "flac", "ogg", "jpg", "jpeg", "png", "gif")


class FfmpegPreviewIn(BaseModel):
    instruction: str = Field(
        ..., min_length=3, max_length=2000,
        description="yêu cầu bằng lời, ví dụ «cắt từ 2:00 đến 2:10»")
    media_url: str | None = Field(None, description="storage key file đã upload")
    source_url: str | None = Field(None, description="link video (yt-dlp tải)")
    remove_sponsor: bool = Field(
        False, description="xoá quảng cáo theo SponsorBlock — CHỈ khi dùng link "
                           "(yt-dlp gắn cờ --sponsorblock-remove khi tải)")


def _input_ext(body: FfmpegPreviewIn) -> str:
    """Đuôi file nguồn để dựng operand hợp đồng `/work/input.<ext>`."""
    if body.media_url:
        name = body.media_url.rsplit("/", 1)[-1]
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        return ext if ext in _KNOWN_EXTS else "mp4"
    # link: lấy đuôi từ path nếu trông như file; YouTube không có → mp4
    from urllib.parse import urlparse

    path = urlparse(body.source_url or "").path
    name = path.rsplit("/", 1)[-1]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext if ext in _KNOWN_EXTS else "mp4"


@router.post("/v1/ffmpeg/preview")
def ffmpeg_preview(body: FfmpegPreviewIn, user: User = Depends(auth),
                   db: Session = Depends(get_db)) -> dict:
    """Dịch yêu cầu bằng lời thành lệnh ffmpeg ĐÃ VALIDATE — CHƯA chạy.

    Trả {command, explanation, warnings, ffmpeg_argv, output_ext, input_name}:
    UI hiện nguyên cụm này, user bấm «Chạy lệnh này» mới tạo job. LLM hỏng
    (JSON bẩn) → 502 với message dịch lại được; chưa cấu hình model → 422.
    """
    instruction = body.instruction.strip()
    if len(instruction) < 3:
        raise HTTPException(status_code=422,
                            detail="Mô tả quá ngắn — gõ rõ bạn muốn làm gì với file")
    if not (body.media_url or body.source_url):
        raise HTTPException(
            status_code=422,
            detail="Cần chọn nguồn trước: upload file hoặc dán link")
    if body.remove_sponsor and not body.source_url:
        raise HTTPException(
            status_code=422,
            detail="«Xoá quảng cáo theo SponsorBlock» chỉ áp dụng khi dùng link "
                   "(cần tải video từ nguồn gốc)")
    # Quyền sở hữu file upload — LLM không được dịch lệnh đọc file người khác.
    if body.media_url:
        parts = body.media_url.split("/")
        owner_ok = (
            user.is_admin
            or (len(parts) >= 2 and parts[0] == "media" and parts[1] == user.id)
            or db.scalar(select(MediaObject)
                         .where(MediaObject.key == body.media_url,
                                MediaObject.user_id == user.id)) is not None)
        if not owner_ok:
            raise HTTPException(status_code=404, detail="file not found")
    if not check_rate(f"ffmpeg:{user.id}", 20):
        raise HTTPException(status_code=429,
                            detail="dịch lệnh quá nhiều lần trong 1 phút — đợi chút")

    from .pipelines.summary import build_chat

    chat = build_chat()
    if chat is None:
        raise HTTPException(
            status_code=422,
            detail="Chưa cấu hình mô hình dịch lệnh — gán model cho công đoạn "
                   "«Tóm tắt» trong Cài đặt AI, hoặc điền bộ dịch trong "
                   "Cấu hình hệ thống")

    system, rules = build_prompt()
    input_ext = _input_ext(body)
    input_name = f"{INPUT_PREFIX}.{input_ext}"
    user_msg = f"{rules}\n\nFile nguồn: {input_name}\nYêu cầu: {instruction}"
    if body.remove_sponsor:
        user_msg += ("\nLưu ý: hệ thống sẽ tự xoá đoạn quảng cáo theo "
                     "SponsorBlock TRƯỚC khi chạy lệnh của bạn — mốc giờ được "
                     "nêu trong yêu cầu tính trên bản ĐÃ xoá quảng cáo.")
    try:
        raw = chat.complete(system, user_msg, temperature=0.1, max_tokens=1500)
    except Exception as exc:  # noqa: BLE001 — LLM hỏng không phải lỗi code
        raise HTTPException(
            status_code=502,
            detail=f"Mô hình dịch lệnh phản hồi lỗi: {str(exc)[:150]}") from exc
    from .pipelines.ffmpeg_cmd import parse_llm_response

    try:
        parsed = parse_llm_response(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail=(f"Mô hình trả về không đúng định dạng ({exc}) — bấm "
                    "«Dịch lại», hoặc viết yêu cầu cụ thể hơn")) from exc
    try:
        argv, sys_warnings = command_to_argv(parsed["command"], input_ext)
    except ValueError as exc:
        # lệnh LLM vi phạm hợp đồng — báo lỗi rõ, KHÔNG tự sửa thay người dùng
        raise HTTPException(
            status_code=502,
            detail=(f"Mô hình sinh lệnh không hợp lệ: {exc} — bấm «Dịch "
                    "lại», hoặc viết yêu cầu cụ thể hơn")) from exc

    out_ext = argv[-1].rsplit(".", 1)[-1]
    warnings = [*sys_warnings, *parsed["warnings"]]
    if body.remove_sponsor:
        warnings.append(
            "Hệ thống tự xoá quảng cáo theo SponsorBlock trước khi chạy lệnh "
            "— mốc giờ trong lệnh tính trên bản đã xoá quảng cáo")
    return {
        "command": " ".join(argv[1:]) if len(argv) > 1 else "",
        "explanation": parsed["explanation"],
        "warnings": warnings,
        "ffmpeg_argv": argv,       # argv đầy đủ (argv[0]="ffmpeg") — job gửi nguyên
        "input_name": input_name,  # để UI hiển thị tên file hợp đồng
        "output_ext": out_ext,
    }
