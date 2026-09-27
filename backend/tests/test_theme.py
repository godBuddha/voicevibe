"""Theme guard — cưỡng chế "mọi màu đi qua token, không hardcode hex".

Vì sao cần: bản UI trước đây rải ~33 mã màu hex trong CSS/inline SVG/JS, nên không thể
thêm chế độ tối mà không bỏ sót chỗ nào. Thay vì tin vào việc "đã sửa hết", test này
kiểm tra bằng máy: bỏ hai khối token ra khỏi CSS thì **không được còn hex nào**, và mọi
token khai ở `:root` phải có bản tương ứng trong `html[data-theme="dark"]` — nếu không,
chế độ tối sẽ có chỗ giữ nguyên màu sáng (chữ trắng trên nền trắng, v.v.).

Kiểm tra:
  1. Mỗi trang: bỏ `:root{...}` + `html[data-theme="dark"]{...}` → không còn hex trong CSS
  2. Mọi token trong `:root` đều có giá trị trong khối dark (trừ số đo layout)
  3. Không có hex trong các `<script>` inline (bảo vệ object màu biểu đồ)
  4. Boot script đặt `data-theme` và nằm TRƯỚC stylesheet (chống nhấp nháy màu)
  5. Token chỉ dùng cho layout (--side-w/--top-h) KHÔNG được nằm trong khối dark

Run:  cd backend && PYTHONPATH=. python tests/test_theme.py
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.admin_ui import ADMIN_HTML  # noqa: E402
from app.app_ui import APP_HTML  # noqa: E402
from app.theme import THEME_CSS  # noqa: E402

PAGES = {"app_ui.py": APP_HTML, "admin_ui.py": ADMIN_HTML}
LAYOUT_METRICS = {"--side-w", "--top-h"}  # không phải màu -> không cần bản tối

STYLE_RE = re.compile(r"<style>(.*?)</style>", re.S)
SCRIPT_RE = re.compile(r"<script>(.*?)</script>", re.S)
ROOT_BLOCK_RE = re.compile(r":root\s*\{[^}]*\}", re.S)
DARK_BLOCK_RE = re.compile(r'html\[data-theme="dark"\]\s*\{[^}]*\}', re.S)
TOKEN_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")
HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def _blocks(css: str) -> tuple[str, str]:
    root = ROOT_BLOCK_RE.search(css)
    dark = DARK_BLOCK_RE.search(css)
    assert root, "không tìm thấy khối :root trong CSS"
    assert dark, 'không tìm thấy khối html[data-theme="dark"] trong CSS'
    return root.group(0), dark.group(0)


def main() -> None:
    root_block, dark_block = _blocks(THEME_CSS)
    root_tokens = dict(TOKEN_RE.findall(root_block))
    dark_tokens = dict(TOKEN_RE.findall(dark_block))

    # 1 + 2) mỗi trang: token phủ đủ, CSS còn lại không hex
    for name, html in PAGES.items():
        styles = STYLE_RE.findall(html)
        assert styles, f"{name}: không tìm thấy <style>"
        for css in styles:
            stripped = ROOT_BLOCK_RE.sub("", DARK_BLOCK_RE.sub("", css))
            leftover = HEX_RE.findall(stripped)
            assert not leftover, (
                f"{name}: còn {len(leftover)} mã màu hardcode ngoài khối token "
                f"{leftover[:6]} — chuyển sang var(--token) trong app/theme.py"
            )

        # 3) không hex trong JS inline
        for i, js in enumerate(SCRIPT_RE.findall(html)):
            bad = HEX_RE.findall(js)
            assert not bad, (
                f"{name}: script #{i} còn màu hardcode {bad[:6]} — "
                "đọc bằng yvCssVar('--chart-...') thay vì viết hex"
            )

        # 4) boot script trước stylesheet
        head = html.split("</head>", 1)[0]
        assert "data-theme" in head, f"{name}: boot script chưa đặt data-theme"
        boot_at = head.find("localStorage.getItem('yv_theme')")
        style_at = head.find("<style>")
        assert boot_at != -1, f"{name}: boot script không đọc 'yv_theme'"
        assert boot_at < style_at, f"{name}: boot script phải nằm TRƯỚC <style>"

    # 2) phủ token
    missing = set(root_tokens) - set(dark_tokens) - LAYOUT_METRICS
    assert not missing, (
        f"token thiếu bản tối: {sorted(missing)} — thêm vào khối "
        'html[data-theme="dark"] trong app/theme.py'
    )
    extra = set(dark_tokens) - set(root_tokens)
    assert not extra, f"khối tối khai token lạ (không có ở :root): {sorted(extra)}"

    # 5) số đo layout không được theme
    for metric in LAYOUT_METRICS:
        assert metric in root_tokens, f"thiếu số đo layout {metric} ở :root"
        assert metric not in dark_tokens, f"{metric} là số đo layout, không nên ở khối tối"

    print(f"không hex ngoài token ({len(PAGES)} trang) ... OK")
    print(f"token phủ đủ sáng+tối ({len(root_tokens)} token) .. OK")
    print("script inline không hardcode màu ......... OK")
    print("boot script trước stylesheet ............ OK")
    print("THEME GUARD PASSED")


if __name__ == "__main__":
    main()