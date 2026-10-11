"""Tự cập nhật yt-dlp bằng binary chính thức từ GitHub release (GC4, C4).

BỐI CẢNH: yt-dlp gãy nhanh theo YouTube (YouTube đổi giao diện, yt-dlp phải
vá theo) — image build 8 ngày trước đã quá cũ khi YouTube đổi. pip upgrade
trong container thì KHÔNG có giá trị dài hạn: container read_only + HOME tmpfs
nên gói cài runtime chết cùng container. Binary chính thức (PyInstaller self-
contained, ~30MB, không cần Python) tải về volume `media` là thứ sống qua
restart — mọi container (api probe + worker download) cùng mount volume này.

- Kênh "stable"  = release mới nhất có nền tảng ổn định (releases/latest).
- Kênh "nightly" = release prerelease mới nhất (ngay sau khi YouTube gãy).
- "off"          = dùng thư viện pip (mặc định — không mạng cũng chạy được).

An toàn: tải vào file tạm CÙNG THƯ MỤC → kiểm SHA-256 theo SHA2-256SUMS của
release → chmod 755 → os.replace (nguyên tử trên cùng filesystem). Binary hỏng
KHÔNG BAO GIỜ được thay binary tốt — sha sai thì giữ nguyên bản cũ và báo lỗi.

Nhà quản lý nguồn tham khảo: youwee (MIT) `src-tauri/src/services/ytdlp.rs` —
kênh stable/nightly + checksum; binary yt-dlp là Public Domain/Unlicense.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import threading
import time

from .manifest import atomic_write_json

GITHUB_REPO = "yt-dlp/yt-dlp"
ASSET = "yt-dlp_linux"
SHA_FILE = "SHA2-256SUMS"
STATE_NAME = "yt-dlp-state.json"
STALE_S = 24 * 3600          # kiểm bản mới tối đa 1 lần/ngày
HTTP_TIMEOUT_S = 60.0
VERSION_TTL_S = 300.0        # cache kết quả probe binary (tránh spawn mỗi call)

_bin_cache: dict = {"prefix": None, "at": 0.0}


def bin_dir(media_root: str | None = None) -> str:
    root = media_root or os.getenv("MEDIA_ROOT", "./media")
    p = os.path.join(root, ".bin")
    os.makedirs(p, exist_ok=True)
    return p


def binary_path(channel: str, media_root: str | None = None) -> str:
    name = "yt-dlp" if channel == "stable" else f"yt-dlp-{channel}"
    return os.path.join(bin_dir(media_root), name)


def read_state(channel: str, media_root: str | None = None) -> dict:
    """Trạng thái lần kiểm cuối — {version, checked_at, sha256, asset_size}."""
    try:
        with open(os.path.join(bin_dir(media_root), f"{STATE_NAME}.{channel}"),
                  encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:  # noqa: BLE001 — chưa từng kiểm
        return {}


def _write_state(channel: str, state: dict, media_root: str | None) -> None:
    atomic_write_json(os.path.join(bin_dir(media_root), f"{STATE_NAME}.{channel}"),
                      state)


def pip_version() -> str | None:
    try:
        return importlib.metadata.version("yt_dlp")
    except Exception:  # noqa: BLE001
        return None


def _default_runner(argv: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(argv, capture_output=True, text=True, timeout=15)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def binary_version(channel: str, media_root: str | None = None,
                   *, runner=None) -> str | None:
    """Version của binary tại chỗ — None nếu thiếu/hỏng (không chạy được)."""
    path = binary_path(channel, media_root)
    if not os.path.isfile(path):
        return None
    run = runner or _default_runner
    try:
        code, out, _err = run([path, "--version"])
        return out or None if code == 0 else None
    except Exception:  # noqa: BLE001 — binary hỏng là chuyện thường
        return None


def resolve_prefix(channel: str, media_root: str | None = None, *,
                   runner=None, ttl: float = VERSION_TTL_S) -> list[str]:
    """argv tiền tố cho subprocess yt-dlp: binary (nếu chạy được) hoặc pip.

    Channel "off" → pip library `[sys.executable, "-m", "yt_dlp"]` (không phụ
    thuộc mạng). Cache TTL tránh probe `--version` mỗi lần tải video.
    """
    global _bin_cache
    now = time.monotonic()
    if channel == "off":
        return [sys.executable, "-m", "yt_dlp"]
    if (_bin_cache["prefix"] is not None and now - _bin_cache["at"] < ttl):
        return _bin_cache["prefix"]
    ver = binary_version(channel, media_root, runner=runner)
    if ver:
        _bin_cache["prefix"] = [binary_path(channel, media_root)]
        _bin_cache["at"] = now
        return _bin_cache["prefix"]
    _bin_cache["prefix"] = None
    _bin_cache["at"] = now
    maybe_autorefresh(channel, media_root=media_root)
    return [sys.executable, "-m", "yt_dlp"]


def reset_cache() -> None:
    """Chỉ dành cho test — xoá cache probe TTL."""
    global _bin_cache
    _bin_cache = {"prefix": None, "at": 0.0}


def _default_http_get(url: str) -> bytes:
    import httpx

    resp = httpx.get(url, timeout=HTTP_TIMEOUT_S, follow_redirects=True,
                     headers={"User-Agent": "voicevibe-selfhost"})
    resp.raise_for_status()
    return resp.content


def fetch_release(channel: str, *, http_get=None) -> dict | None:
    """Meta release mới nhất theo kênh — {tag, asset_url, sha_url}; None nếu
    không xác định được (mạng lỗi là chuyện của caller — nuốt ở refresh)."""
    http_get = http_get or _default_http_get
    if channel == "stable":
        data = json.loads(http_get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"))
        assets = {a["name"]: a["browser_download_url"] for a in data["assets"]}
    else:
        data = json.loads(http_get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=10"))
        rel = next((r for r in data if r.get("prerelease")), None)
        if rel is None:
            return None
        assets = {a["name"]: a["browser_download_url"] for a in rel["assets"]}
        data = {"tag_name": rel["tag_name"]}
    if ASSET not in assets or SHA_FILE not in assets:
        return None
    return {"tag": data["tag_name"],
            "asset_url": assets[ASSET], "sha_url": assets[SHA_FILE]}


def _parse_sha_file(content: str, asset: str) -> str | None:
    for line in content.splitlines():
        m = re.match(r"^\s*([0-9a-fA-F]{64})\s+\*?(.+)$", line)
        if m and os.path.basename(m.group(2).strip()) == asset:
            return m.group(1).lower()
    return None


def refresh(channel: str, *, force: bool = False, http_get=None,
            media_root: str | None = None, now: float | None = None) -> dict:
    """Tải + kiểm + cài binary. Trả {"version","path"} hoặc {"skipped":"fresh"}.

    Nhập vai "không bao giờ để binary hỏng thay binary tốt": tải tmp CÙNG thư
    mục → verify sha256 → os.replace nguyên tử.
    """
    now = now or time.time()
    state = read_state(channel, media_root)
    if not force and state.get("checked_at") and \
            now - state["checked_at"] < STALE_S:
        return {"skipped": "fresh", "version": state.get("version")}
    meta = fetch_release(channel, http_get=http_get)
    if meta is None:
        raise ValueError("không đọc được bản mới từ GitHub — giữ nguyên bản cũ")
    binary = http_get(meta["asset_url"])
    expected = _parse_sha_file(http_get(meta["sha_url"]).decode(
        "utf-8", "replace"), ASSET)
    got = hashlib.sha256(binary).hexdigest()
    if not expected:
        raise ValueError("không đọc được checksum SHA2-256SUMS — giữ nguyên bản cũ")
    if got != expected:
        raise ValueError("checksum không khớp — giữ nguyên bản cũ (binary tải về "
                         "không đáng tin)")
    path = binary_path(channel, media_root)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(binary)
    os.chmod(tmp, 0o755)
    os.replace(tmp, path)  # nguyên tử trên cùng filesystem
    state = {"version": meta["tag"], "checked_at": int(now), "sha256": got,
             "asset_size": len(binary)}
    _write_state(channel, state, media_root)
    reset_cache()
    return {"version": meta["tag"], "path": path}


def maybe_autorefresh(channel: str, *, media_root: str | None = None,
                      now: float | None = None) -> None:
    """Kick kiểm bản mới NỀN (thread daemon) — job KHÔNG block, chạy tiếp bằng
    binary hiện tại, lần sau dùng bản mới. Lỗi mạng nuốt trong thread."""
    now = now or time.time()
    if channel == "off":
        return
    state = read_state(channel, media_root)
    if state.get("checked_at") and now - state["checked_at"] < STALE_S:
        return

    def _bg():
        try:
            refresh(channel, media_root=media_root, now=now)
        except Exception:  # noqa: BLE001 — nền, không giết ai; checked_at KHÔNG
            pass           # cập nhật khi lỗi → lần sau vẫn thử lại

    threading.Thread(target=_bg, daemon=True, name="ytdlp-autorefresh").start()
