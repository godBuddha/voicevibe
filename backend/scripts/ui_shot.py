"""UI smoke + screenshot tool — drives the real app in headless Chrome.

Two jobs, both valuable:
  1. SMOKE: opens every panel and FAILS (exit 1) on any uncaught page error.
     This is how two real bugs were caught — a broken `flash("\\"")` escape that
     killed the whole inline UI, and `go('voices')` calling an undefined
     `loadVoices()` (panel never opened). Neither shows up in Python tests.
  2. SHOTS: writes the README screenshots to docs/screenshots/ — including the
     dark-mode shots, taken by flipping the real theme function and asserting
     `data-theme` actually changed (a theme that silently fails to apply would
     otherwise ship unnoticed).

Needs Playwright + a Chrome/Chromium binary:
  uv run --with playwright python backend/scripts/ui_shot.py            # shots
  uv run --with playwright python backend/scripts/ui_shot.py --check     # smoke only
  uv run --with playwright python backend/scripts/ui_shot.py --no-demo   # use env DB/media

Options: --out DIR (default <repo>/docs/screenshots), --port N (default: free),
         --chrome PATH (default: google-chrome).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

REPO = pathlib.Path(__file__).resolve().parents[2]
# Tài khoản demo cho DB TẠM của script này (không phải thông tin thật).
ADMIN_EMAIL = "admin@demo.local"
DEMO_PASSWORD = "demo-password-123"

PANELS = [  # (screenshot name, app router target, element that must be visible)
    ("02-dub", "dub", "#dubfile"),
    ("03-tts", "tts", "#ttstext"),
    ("04-voices", "voices", "#voicelist"),
    ("05-jobs", "jobs", "#joblist"),
    ("06-api-keys", "api", "#keylist"),
    ("12-subtitle", "subtitle", "#subfile"),
    ("13-settings", "settings", "#sesslist"),
]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def seed_demo() -> None:
    """Throwaway dev DB with demo rows so the UI isn't empty in screenshots.

    Phase 2: UI xác thực bằng phiên, nên cần một Admin ĐĂNG NHẬP ĐƯỢC. Script tạo
    admin + user demo với mật khẩu đã biết (DB này là tạm, xoá sau khi chụp).
    """
    from sqlalchemy import select

    from app.db import SessionLocal, engine
    from app.migrations import ensure_schema
    from app.models import Job, JobStatus, ROLE_ADMIN, User, Voice
    from app.security import hash_password

    ensure_schema(engine)
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == ADMIN_EMAIL)):
            return
        admin = User(email=ADMIN_EMAIL, role=ROLE_ADMIN,
                     password_hash=hash_password(DEMO_PASSWORD))
        db.add(admin)
        db.flush()
        u = User(email="creator@demo",
                 password_hash=hash_password(DEMO_PASSWORD))
        db.add(u)
        db.flush()
        db.add(Voice(user_id=u.id, name="Giọng của Long", lang="vi",
                     engine="vieneu", ref_s3_key="voices/demo/ref.wav"))
        db.add(Voice(user_id=u.id, name="Mai Anh (preset)", lang="vi",
                     engine="vieneu", ref_s3_key=""))
        for t, st, pr, key in [("dub", JobStatus.done, 100, None),
                               ("stt", JobStatus.done, 100, "jobs/demo/transcript.srt"),
                               ("tts", JobStatus.running, 45, None),
                               ("translate", JobStatus.queued, 0, None)]:
            db.add(Job(user_id=u.id, type=t, status=st, progress=pr,
                       result_s3_key=key, params={"type": t}))

        # Nhà cung cấp AI demo để tab AI không trống trong ảnh chụp — khoá là giá trị
        # GIẢ, và chỉ hiển thị dạng mask nên không lộ gì.
        from app.models import AiProvider, StageModel
        from app.providers_api import _encrypt, _hint

        ds = AiProvider(name="DeepSeek API", kind="openai",
                        base_url="https://api.deepseek.com/v1",
                        api_key_enc=_encrypt("sk-demo-khong-phai-key-that-1234"),
                        api_key_hint=_hint("sk-demo-khong-phai-key-that-1234"))
        ol = AiProvider(name="Ollama local", kind="ollama",
                        base_url="http://localhost:11434")
        db.add_all([ds, ol])
        db.flush()
        db.add(StageModel(stage="translate", provider_id=ds.id,
                          model="deepseek-chat", order=0))
        db.commit()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "docs" / "screenshots"))
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--chrome", default="google-chrome")
    ap.add_argument("--check", action="store_true", help="smoke only, no screenshots")
    ap.add_argument("--no-demo", action="store_true", help="don't seed demo rows")
    args = ap.parse_args()

    sys.path.insert(0, str(REPO / "backend"))
    os.environ.setdefault("PYTHONPATH", str(REPO / "backend"))
    os.environ["VOICEVIBE_INLINE"] = "1"
    if not args.no_demo:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="vv_ui_"))
        os.environ.setdefault("MEDIA_ROOT", str(tmp / "media"))
        os.environ.setdefault("DATABASE_URL", f"sqlite:///{tmp}/ui.db")
        seed_demo()

    port = args.port or free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=str(REPO / "backend"), env={**os.environ},
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(30):
            try:
                urllib.request.urlopen(f"{base}/healthz", timeout=2).read()
                break
            except Exception:
                time.sleep(1)
        else:
            print("FAIL: app server did not start")
            return 1

        from playwright.sync_api import sync_playwright

        # Playwright needs an absolute executable path; fall back to its own
        # bundled Chromium when no system Chrome is found.
        chrome = shutil.which(args.chrome) or shutil.which("chromium") \
            or shutil.which("chromium-browser") or args.chrome
        launch_args = ["--no-sandbox", "--disable-gpu"]
        if not pathlib.Path(chrome).is_file():
            chrome = None  # let Playwright use its bundled browser
            print("note: no system Chrome found — using Playwright's Chromium")

        out_dir = pathlib.Path(args.out)
        errors: list[str] = []
        shots = 0

        with sync_playwright() as p:
            browser = p.chromium.launch(**({"executable_path": chrome} if chrome else {}),
                                        args=launch_args)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

            def shot(name: str) -> None:
                nonlocal shots
                if args.check:
                    return
                out_dir.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(out_dir / f"{name}.png"), full_page=True)
                shots += 1

            # --- Đăng nhập bằng phiên (Phase 2): / chuyển về /login khi chưa có phiên.
            page.goto(f"{base}/")
            page.wait_for_selector("#email", timeout=20000)
            shot("00-login")
            page.fill("#email", ADMIN_EMAIL)
            page.fill("#password", DEMO_PASSWORD)
            page.click("#submit")
            # Admin đăng nhập xong được đưa tới /admin (đúng hành vi sản phẩm), nên
            # chờ RỜI khỏi /login rồi tự mở trang ứng dụng để chụp.
            page.wait_for_url(lambda url: "/login" not in url, timeout=20000)
            page.goto(f"{base}/")
            page.wait_for_selector("#shell", state="visible", timeout=20000)
            page.wait_for_timeout(1200)

            # AGPL §13: liên kết "Mã nguồn" phải THỰC SỰ tiếp cận được, không chỉ
            # tồn tại trong DOM. Sidebar dài + fixed nên rất dễ bị đẩy xuống dưới
            # màn hình mà không ai nhận ra khi chỉ nhìn code.
            link = page.locator('.side-foot a')
            assert link.count() == 1, "thiếu liên kết Mã nguồn (AGPL §13)"
            box = link.bounding_box()
            vh = page.viewport_size["height"]
            assert box and box["y"] + box["height"] <= vh, (
                f"liên kết Mã nguồn nằm ngoài màn hình (y={box and box['y']:.0f}, "
                f"viewport={vh}) — thu gọn sidebar để nó hiển thị được"
            )

            shot("01-dashboard")

            for name, target, sel in PANELS:
                page.evaluate(f"go('{target}')")  # app's own router
                page.wait_for_selector(sel, state="visible", timeout=15000)
                page.wait_for_timeout(700)
                shot(name)

            # --- Trang quản trị: phiên đang là admin nên vào thẳng, không cần key.
            # Tab mặc định là "AI" (nhà cung cấp/model/công đoạn/prompt).
            page.goto(f"{base}/admin")
            page.wait_for_selector("#ai .card", timeout=20000)
            page.wait_for_timeout(700)
            shot("07-admin-ai")
            page.click("#tab-settings")
            page.wait_for_selector("#content .card", timeout=20000)
            page.wait_for_timeout(500)
            shot("11-admin-settings")
            page.click("#tab-users")
            page.wait_for_selector("#users table.users", timeout=20000)
            page.wait_for_timeout(500)
            shot("10-admin-users")
            page.click("#tab-audit")
            page.wait_for_selector("#audit table.users", timeout=20000)
            page.wait_for_timeout(500)
            shot("14-admin-audit")

            # Chế độ tối: bật qua đúng hàm của UI rồi kiểm tra theme đã đổi thật.
            page.goto(f"{base}/")
            page.wait_for_selector("#shell", state="visible", timeout=20000)
            page.wait_for_timeout(1000)
            page.evaluate("vvSetTheme('dark')")
            page.wait_for_timeout(600)
            applied = page.evaluate(
                "document.documentElement.getAttribute('data-theme')")
            assert applied == "dark", f"theme không đổi sang dark (nhận {applied!r})"
            shot("08-dashboard-dark")
            page.evaluate("go('dub')")
            page.wait_for_selector("#dubfile", state="visible", timeout=15000)
            page.wait_for_timeout(500)
            shot("09-dub-dark")
            # trả về sáng để ảnh admin/những lần chạy sau không bị lệch
            page.evaluate("vvSetTheme('light')")

            browser.close()

        if errors:
            print("UI SMOKE FAILED — uncaught page errors:")
            for e in dict.fromkeys(errors):
                print("  -", e)
            return 1
        print(f"UI SMOKE PASSED — all panels rendered, 0 page errors"
              + (f", {shots} screenshots -> {out_dir}" if shots else ""))
        return 0
    finally:
        server.terminate()


if __name__ == "__main__":
    raise SystemExit(main())