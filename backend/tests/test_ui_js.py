"""UI JS syntax guard — catches broken inline JavaScript in the served HTML.

Regression test: app_ui.py shipped `flash("🚧 \\"" + ...)` inside a NON-raw
Python string, so Python ate the backslash and the browser got
`flash("🚧 "" + name + "" ...)` — a syntax error that silently killed the
ENTIRE inline UI (gate never opened, no console-visible test caught it).

The extractor mimics the browser: it reads the string as Python produces it
(so escaping bugs surface), then runs `node --check` on each inline script.
Skips cleanly when node is unavailable (still validates the extraction).

Run:  cd backend && PYTHONPATH=. python tests/test_ui_js.py
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.admin_ui import ADMIN_HTML  # noqa: E402
from app.app_ui import APP_HTML  # noqa: E402
from app.auth_ui import LOGIN_HTML, SETUP_HTML  # noqa: E402

PAGES = {"app_ui.py": APP_HTML, "admin_ui.py": ADMIN_HTML,
         "auth_ui.py (login)": LOGIN_HTML, "auth_ui.py (setup)": SETUP_HTML}
SCRIPT_RE = re.compile(r"<script>(.*?)</script>", re.S)

# Mỗi trang có ít nhất một script "thật" (logic của trang). Ngoài ra có boot script
# theme — cố tình RẤT NGẮN (chạy trước stylesheet để chống nhấp nháy màu), nên điều
# kiện >200 ký tự áp cho TỪNG script như trước là sai.
MIN_MAIN_SCRIPT = 200


def inline_scripts(html: str) -> list[str]:
    return [s for s in SCRIPT_RE.findall(html) if s.strip()]


def main() -> None:
    node = shutil.which("node")
    total = 0
    for name, html in PAGES.items():
        scripts = inline_scripts(html)
        assert scripts, f"{name}: no inline <script> found — extraction broken?"
        # Ít nhất MỘT script phải là logic thật của trang; nếu JS của trang biến mất
        # thì chỉ còn boot script theme và test này phải bắt được.
        assert any(len(s) > MIN_MAIN_SCRIPT for s in scripts), (
            f"{name}: không có script nào > {MIN_MAIN_SCRIPT} ký tự — "
            "JS của trang có thể đã biến mất (chỉ còn boot script theme?)"
        )
        for i, js in enumerate(scripts):
            total += 1
            if not node:
                continue
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
                f.write(js)
                tmp = f.name
            try:
                r = subprocess.run([node, "--check", tmp], capture_output=True, text=True)
                assert r.returncode == 0, f"{name} script #{i} has a JS syntax error:\n{r.stderr}"
            finally:
                os.unlink(tmp)

    if node:
        print(f"inline JS syntax ({total} scripts) ..... OK")
    else:
        print(f"inline JS extraction ({total} scripts) .. OK (node missing — syntax not checked)")

    # --- Mọi <section id="page-X"> phải nằm trong mảng PAGES của router.
    # Router `go(page)` chỉ bật section nào có trong PAGES; thêm một trang mà quên
    # nối vào danh sách thì trang đó KHÔNG BAO GIỜ hiện, không lỗi JS, không cảnh
    # báo — sidebar bấm vào không có gì xảy ra. Đã gặp thật với trang `subtitle`
    # (chỉ lộ ra khi chụp ảnh: "waiting for locator #subfile to be visible").
    m = re.search(r"const PAGES\s*=\s*\[([^\]]*)\]", APP_HTML)
    assert m, "không tìm thấy mảng PAGES trong app_ui.py"
    pages = {p.strip().strip('"\'') for p in m.group(1).split(",") if p.strip()}
    sections = set(re.findall(r'<section id="page-([\w-]+)"', APP_HTML))
    assert sections, "không tìm thấy <section id='page-…'> nào"
    missing = sorted(sections - pages)
    assert not missing, (
        f"các trang có markup nhưng KHÔNG có trong PAGES (sẽ không bao giờ hiện): {missing}")
    orphan = sorted(pages - sections)
    assert not orphan, f"PAGES có trang không tồn tại markup: {orphan}"
    print(f"PAGES khớp markup ({len(pages)} trang) ..... OK")

    # --- Mọi mục sidebar có data-page phải trỏ tới trang tồn tại (nếu không,
    # bấm vào là `go()` âm thầm không làm gì).
    targets = set(re.findall(r'class="nav"[\s\S]*?</nav>', APP_HTML))
    nav = targets.pop() if targets else ""
    bad = sorted({d for d in re.findall(r'data-page="([\w-]+)"', nav)} - pages)
    assert not bad, f"sidebar trỏ tới trang không có trong PAGES: {bad}"
    print("sidebar trỏ tới trang hợp lệ ......... OK")

    print("UI JS GUARD PASSED")


if __name__ == "__main__":
    main()