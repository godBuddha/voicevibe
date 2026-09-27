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

PAGES = {"app_ui.py": APP_HTML, "admin_ui.py": ADMIN_HTML}
SCRIPT_RE = re.compile(r"<script>(.*?)</script>", re.S)


def inline_scripts(html: str) -> list[str]:
    return [s for s in SCRIPT_RE.findall(html) if s.strip()]


def main() -> None:
    node = shutil.which("node")
    total = 0
    for name, html in PAGES.items():
        scripts = inline_scripts(html)
        assert scripts, f"{name}: no inline <script> found — extraction broken?"
        for i, js in enumerate(scripts):
            total += 1
            # Cheap structural sanity even without node: unbalanced crude check
            # is unreliable for JS, so only assert the extraction is non-trivial.
            assert len(js) > 200, f"{name}: script #{i} suspiciously short"
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
    print("UI JS GUARD PASSED")


if __name__ == "__main__":
    main()