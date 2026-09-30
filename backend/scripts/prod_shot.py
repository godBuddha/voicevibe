"""Chụp ảnh stack PROD đang chạy bằng docker compose (không phải dev inline).

Khác `ui_shot.py`: script kia chạy app trong tiến trình con với SQLite tạm để sinh
ảnh README. Script này trỏ vào một stack compose THẬT đang chạy (Postgres + Redis +
api + worker) và chỉ chụp — mục đích là bằng chứng "bản prod chạy được", không phải
sinh ảnh tài liệu.

Dùng:
  python backend/scripts/prod_shot.py --base http://127.0.0.1:18080 \
      --email admin@local --password ... [--out docs/verification]
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:18080")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--out", default="docs/verification")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    chrome = (shutil.which("google-chrome") or shutil.which("chromium")
              or shutil.which("chromium-browser"))
    errors: list[str] = []
    shots = 0

    with sync_playwright() as p:
        b = p.chromium.launch(**({"executable_path": chrome} if chrome else {}),
                              args=["--no-sandbox", "--disable-gpu"])
        ctx = b.new_context(viewport={"width": 1440, "height": 950})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(args.base, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#email, #shell", timeout=30000)
        if page.locator("#email").count():
            page.fill("#email", args.email)
            page.fill("#password", args.password)
            page.click("#submit")
            page.wait_for_url(lambda u: "/login" not in u, timeout=30000)
        page.goto(args.base, wait_until="domcontentloaded")
        page.wait_for_selector("#shell", state="visible", timeout=30000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(out / "prod-01-dashboard.png"), full_page=True)
        shots += 1

        # tab Jobs: cho thấy job đã chạy qua worker THẬT tới kết quả
        page.evaluate("go('jobs')")
        page.wait_for_selector("#joblist", timeout=20000)
        page.wait_for_timeout(1200)
        page.screenshot(path=str(out / "prod-02-jobs.png"), full_page=True)
        shots += 1

        page.goto(f"{args.base}/admin", wait_until="domcontentloaded")
        page.wait_for_selector("#ai .card", timeout=30000)
        page.wait_for_timeout(1200)
        page.screenshot(path=str(out / "prod-03-admin.png"), full_page=True)
        shots += 1

        b.close()

    if errors:
        print("PAGE ERRORS:", *dict.fromkeys(errors), sep="\n  ")
        return 1
    print(f"PROD SHOTS OK — {shots} ảnh -> {out}, 0 page error")
    return 0


if __name__ == "__main__":
    sys.exit(main())