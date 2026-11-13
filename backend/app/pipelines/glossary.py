"""GD2 — Thuật ngữ bắt buộc (glossary) cho dịch thuật.

Vấn đề: LLM dịch tự do — tên riêng/code name mỗi câu một kiểu ("OpenAI" có
lúc thành "Mở AI", "Gióng" có lúc thành "Phù Đổng"). Người làm video cần
CỘT THUẬT NGỮ: vài cặp `gốc=bản dịch` mà MỌI câu phải dịch theo.

Ba hàm thuần (không đụng DB/mạng — pipelines cố tình DB-free):
  parse_glossary(text)    → list cặp; sai format ném ValueError KÈM SỐ DÒNG —
                            validate chặn LÚC TẠO JOB (422), không để worker
                            chết giữa đường.
  glossary_block(pairs)   → khối chữ chèn CUỐI system prompt — ràng buộc cứng:
                            override Thư viện Prompt không xoá được danh sách.
  check_translations(...) → CẢNH BÁO, không raise: LLM không tôn trọng ràng
                            buộc là chuyện đã kiểm chứng (oss-references mục 5
                            — không assert cứng trên đầu ra LLM). Bản dịch vi
                            phạm vẫn được dùng; người dùng THẤY cảnh báo trong
                            job và tự quyết (chạy lại với prompt khác).

Chỉ kiểm khi câu GỐC có chứa thuật ngữ — câu gốc không nói tới thì bản dịch
chứa từ đó cũng không phải vi phạm (tránh báo nhầm).
"""
from __future__ import annotations

import re

# Bảng chữ CJK/hangul/kana — từ không có khoảng trắng thì biên từ `\b` vô
# nghĩa, phải so substring.
_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")


def parse_glossary(text: str) -> list[tuple[str, str]]:
    """Đọc danh sách thuật ngữ: mỗi dòng `gốc=bản dịch` (dấu `=` ĐẦU TIÊN là
    ranh giới — bản dịch được chứa `=`). Dòng trống và `#` comment bị bỏ.
    Sai format ném ValueError kèm số dòng để UI chỉ đúng chỗ cho người dùng.
    """
    pairs: list[tuple[str, str]] = []
    for lineno, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(
                f"dòng {lineno}: thiếu dấu '=' (định dạng: gốc=bản dịch)")
        origin, _, replacement = line.partition("=")
        origin, replacement = origin.strip(), replacement.strip()
        if not origin or not replacement:
            raise ValueError(
                f"dòng {lineno}: phía trước hoặc sau '=' bị trống")
        pairs.append((origin, replacement))
    return pairs


def glossary_block(pairs: list[tuple[str, str]]) -> str:
    """Khối chèn CUỐI system prompt — mệnh lệnh rõ, đặt trên mọi chỉ dẫn
    về văn phong (nối sau cùng để override không xoá nhầm)."""
    lines = ["BỘ THUẬT NGỮ BẮT BUỘC (ràng buộc cao hơn mọi chỉ dẫn khác):"]
    for origin, replacement in pairs:
        lines.append(f'- LUÔN dịch "{origin}" thành "{replacement}" trong MỌI '
                     "câu, kể cả khi ngữ cảnh gợi ý cách khác.")
    lines.append("- TUYỆT ĐỐI KHÔNG giữ lại từ gốc trong bản dịch.")
    return "\n".join(lines)


def _contains(text: str, term: str) -> bool:
    """Tồn tại `term` trong `text`? So KHÔNG PHÂN BIỆT HOA/thường; có biên từ
    (`\\b`) khi thuật ngữ không phải CJK — tránh báo nhầm "cat" trong
    "category"; CJK thì substring (tiếng không có khoảng trắng giữa từ)."""
    if not text or not term:
        return False
    if _CJK.search(term):
        return term.casefold() in text.casefold()
    return re.search(r"\b" + re.escape(term) + r"\b", text,
                     re.IGNORECASE) is not None


def check_translations(origins: list[str], translations: list[str],
                       pairs: list[tuple[str, str]], *,
                       max_warnings: int = 20) -> list[str]:
    """Cảnh báo câu nào vẫn GIỮ từ gốc. Chỉ đếm khi câu gốc CÓ thuật ngữ
    (câu gốc không nói tới thì không phải vi phạm). 1 cảnh báo/câu là đủ —
    dồn dập thì người dùng không đọc nổi. Tối đa `max_warnings` rồi dừng."""
    warnings: list[str] = []
    for i, tr_text in enumerate(translations):
        src = origins[i] if i < len(origins) else ""
        for origin, _replacement in pairs:
            if _contains(src, origin) and _contains(tr_text, origin):
                warnings.append(f"câu {i + 1}: vẫn giữ «{origin}» trong bản dịch")
                break
        if len(warnings) >= max_warnings:
            warnings.append(f"(còn nữa — dừng ở {max_warnings} cảnh báo)")
            break
    return warnings


def _selftest() -> None:
    # --- parse: đúng format, comment, dòng trống
    pairs = parse_glossary("# comment\nOpenAI=OpenAI (công ty)\n\nGióng=Gióng\n")
    assert pairs == [("OpenAI", "OpenAI (công ty)"), ("Gióng", "Gióng")], pairs
    # `=` đầu tiên là ranh giới — bản dịch chứa `=` vẫn hợp lệ
    assert parse_glossary("a=b=c") == [("a", "b=c")]
    # --- parse: sai format ném lỗi kèm số dòng
    for bad, frag in [("không có dấu bằng", "dòng 1"), ("ok=sau\n\nx", "dòng 3"),
                      ("=trống", "dòng 1"), ("trống=", "dòng 1")]:
        try:
            parse_glossary(bad)
        except ValueError as exc:
            assert frag in str(exc), (bad, str(exc))
        else:
            raise AssertionError(f"phải báo lỗi: {bad!r}")
    # --- block: chứa lệnh cứng + từng cặp
    block = glossary_block([("OpenAI", "OpenAI (công ty)")])
    assert "BỘ THUẬT NGỮ BẮT BUỘC" in block and "OpenAI" in block, block
    # --- check: vi phạm được bắt (không phân biệt hoa/thường), đúng số câu
    warn = check_translations(["Nó nhanh như OpenAI nhé.", "Câu sạch."],
                              ["Nó nhanh như OpenAI (công ty).", "Clean."],
                              [("OpenAI", "OpenAI (công ty)")])
    assert warn == ["câu 1: vẫn giữ «OpenAI» trong bản dịch"], warn
    # --- check: biên từ — "cat" không khớp trong "category"
    assert check_translations(["category listing"], ["category listing"],
                              [("cat", "mèo")]) == []
    # --- check: câu gốc KHÔNG chứa thuật ngữ → không cảnh báo dù bản dịch chứa
    assert check_translations(["chào buổi sáng"], ["chào buổi sáng OpenAI"],
                              [("OpenAI", "OpenAI (công ty)")]) == []
    # --- check: CJK so substring
    assert check_translations(["桜が咲く"], ["桜が咲く"], [("桜", "hoa anh đào")]) != []
    # --- check: cap số lượng
    many = check_translations(["a OpenAI"] * 30, ["a OpenAI"] * 30,
                              [("OpenAI", "X")])
    assert len(many) == 21 and "dừng ở 20" in many[-1], many
    print("parse_glossary ............. OK")
    print("glossary_block ............. OK")
    print("check_translations ......... OK")
    print("GLOSSARY SELFTEST PASSED")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
