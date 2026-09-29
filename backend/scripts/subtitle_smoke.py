"""Phụ đề trên GPU thật: STT + tách người nói -> SRT/VTT/ASS (+ song ngữ vi->en).

Kiểm chứng đường thật, không phải mock: file mẫu 2 người nói có sẵn trên box.

Chạy trên box GPU:
  cd /workspace/voicevibe && source .venv/bin/activate
  cd backend && PYTHONPATH=. python scripts/subtitle_smoke.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MEDIA_ROOT", "/workspace/media")
os.environ.setdefault(
    "DATABASE_URL", "sqlite:////workspace/voicevibe/backend/voicevibe.db")

from app.pipelines.stt import diarize, merge, transcribe  # noqa: E402
from app.pipelines.subtitle import render  # noqa: E402
from app.pipelines.translate import build_translator  # noqa: E402

SRC = "/workspace/samples/d3_2spk.wav"
OUT = "/workspace/evidence"


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    print(f"[src] {SRC}")

    segs, info = transcribe(SRC, language="vi")
    print(f"[stt] {len(segs)} segment, ngôn ngữ {info.language} "
          f"p={info.language_probability:.2f}")
    turns = diarize(SRC)
    attributed = merge(segs, turns)
    speakers = sorted({s.speaker for s in attributed if s.speaker})
    print(f"[diarize] {len(turns)} lượt nói, người nói: {speakers}")
    assert len(segs) >= 2, "cần ít nhất 2 segment để bài kiểm có nghĩa"

    # --- ba định dạng, bản gốc
    for fmt in ("srt", "vtt", "ass"):
        text = render(attributed, fmt)
        path = f"{OUT}/subtitle.{fmt}"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"[{fmt}] {len(text)} ký tự -> {path}")

    srt = render(attributed, "srt")
    assert "00:00:00," in srt, srt[:120]
    assert "Người 1" in srt, srt[:400]           # nhãn người nói đọc được
    vtt = render(attributed, "vtt")
    assert vtt.lstrip().startswith("WEBVTT")
    assert "00:00:00." in vtt
    ass = render(attributed, "ass")
    assert "[V4+ Styles]" in ass and "0:00:00.00" in ass
    print("[check] 3 định dạng đúng quy ước thời gian của chúng")

    # --- song ngữ vi->en (dùng đúng translator mà pipeline thật dùng)
    tr = build_translator("vi", "en")
    translations = [tr.translate(s.text) if s.text.strip() else "" for s in attributed]
    bi = render(attributed, "srt", translations=translations, bilingual=True)
    with open(f"{OUT}/subtitle-bilingual.srt", "w", encoding="utf-8") as fh:
        fh.write(bi)

    blocks = [b for b in bi.split("\n\n") if b.strip()]
    assert len(blocks) == len(attributed), (len(blocks), len(attributed))
    for b in blocks:
        assert len(b.splitlines()[2:]) == 2, f"cue không phải 2 dòng: {b!r}"
    print(f"[check] song ngữ: {len(blocks)} cue, mỗi cue đúng 2 dòng")

    bi_ass = render(attributed, "ass", translations=translations, bilingual=True)
    with open(f"{OUT}/subtitle-bilingual.ass", "w", encoding="utf-8") as fh:
        fh.write(bi_ass)
    assert all(r"\N" in l for l in bi_ass.splitlines() if l.startswith("Dialogue:"))
    print("[check] ASS song ngữ dùng \\N")

    print("\n--- SRT (bản gốc) ---")
    print("\n".join(srt.splitlines()[:9]))
    print("\n--- SRT (song ngữ, 1 cue) ---")
    print(blocks[0])
    print(f"\nDỮ LIỆU PHỤ ĐỀ: {len(attributed)} cue, người nói {speakers}")
    print("SUBTITLE SMOKE PASSED")


if __name__ == "__main__":
    main()