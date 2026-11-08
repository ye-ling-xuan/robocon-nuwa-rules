"""Extract a reviewable draft from the supplied V3 PDF; never invent page numbers.

V3 body uses 12pt and its editorial notes use smaller type. Review output when
replacing the PDF: this parser deliberately does not claim to understand layouts
of future versions. Coordinates are PyMuPDF top-left PDF points, before zoom.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import unicodedata
from pathlib import Path

import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "server" / "data"
KEYWORDS = [
    "五色石", "携带", "塔基", "中段", "塔顶", "保护法则", "全塔", "同时", "公共区",
    "TR", "BR", "L1", "L2", "传递区", "地面区", "建塔处", "储存区", "坡道", "阶梯",
    "机器人", "运行区域", "翻转", "重试", "犯规", "强制", "禁用", "失误", "掉落",
    "得分", "记分", "分值", "核查", "破平", "持平", "比赛场地", "比赛用品", "启动",
    "尺寸", "重量", "通信", "暂停", "安全", "电池", "电压", "中央基座", "同时耸立",
]
HIGHLIGHTS = {
    "3.6.8": "携带五色石的机器人不得携带任何塔基/中段/塔顶。",
    "4.4.2": "携带五色石时不得携带其它比赛用品。",
}
RELATED = {
    "3.6.8": ["4.4.2", "6.5"], "4.4.2": ["3.6.8", "6.5"],
    "6.5": ["4.4.2", "5.3.3"], "3.6.1": ["2.22", "3.5.7", "3.6.2", "4.5.1"],
    "8.1.3": ["8.1.2", "8.1.4", "8.1.6"], "8.1.5": ["3.6.9"],
    "9.2": ["9.1"],
}


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).lower()


def body_lines(page) -> list[dict]:
    """Keep actual rule text, excluding small editorial boxes and page footers."""
    lines = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            chars = [c for span in line["spans"] if span["size"] >= 11.8 for c in span["chars"]]
            text = "".join(c["c"] for c in chars).strip()
            if not text:
                continue
            lines.append({"text": text, "bbox": list(line["bbox"]), "chars": chars})
    # Table cells have slightly different baselines. Sort by a common row then x.
    lines.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))
    rows: list[dict] = []
    for line in lines:
        if rows and abs(rows[-1]["bbox"][1] - line["bbox"][1]) < 2:
            rows[-1]["cells"].append(line)
        else:
            rows.append({"bbox": line["bbox"], "cells": [line]})
    result = []
    for row in rows:
        cells = sorted(row["cells"], key=lambda c: c["bbox"][0])
        bbox = fitz.Rect(cells[0]["bbox"])
        for cell in cells[1:]:
            bbox |= fitz.Rect(cell["bbox"])
        result.append({"text": " ".join(c["text"] for c in cells), "bbox": list(bbox),
                       "chars": [c for cell in cells for c in cell["chars"]]})
    return result


def quote_rects(lines: list[dict], quote: str) -> list[list[float]]:
    chars = [c for line in lines for c in line["chars"] if not c["c"].isspace()]
    haystack = "".join(normalize(c["c"]) for c in chars)
    needle = normalize(quote)
    start = haystack.find(needle)
    if start < 0:
        raise ValueError(f"Highlight quote is absent: {quote}")
    # V3's body contains no characters expanding into multiple NFKC characters.
    if len(haystack) != len(chars):
        raise ValueError("Character normalization changed length; review extraction")
    boxes: list[fitz.Rect] = []
    for char in chars[start:start + len(needle)]:
        rect = fitz.Rect(char["bbox"])
        if boxes and abs(boxes[-1].y0 - rect.y0) < 3:
            boxes[-1] |= rect
        else:
            boxes.append(rect)
    return [[round(v, 2) for v in box] for box in boxes]


def extract(pdf: Path, output: Path, start_page: int = 9, end_page: int = 29) -> list[dict]:
    output.mkdir(parents=True, exist_ok=True)
    clauses = []
    current = None
    chapter = ""
    section = ""
    doc = fitz.open(pdf)

    def finish():
        if not current:
            return
        segments = []
        for page_number, lines in current["lines"].items():
            text = "\n".join(line["text"] for line in lines)
            rects = quote_rects(lines, text)
            box = fitz.Rect(rects[0])
            for rect in rects[1:]:
                box |= fitz.Rect(rect)
            segments.append({"page": page_number, "quote": text, "bbox": [round(v, 2) for v in box], "rects": rects})
        text = "\n".join(s["quote"] for s in segments)
        first_lines = next(iter(current["lines"].values()))
        # Stop a default excerpt at an editorial box or large layout gap.
        continuous = []
        for line in first_lines:
            if continuous and line["bbox"][1] - continuous[-1]["bbox"][1] > 32:
                break
            continuous.append(line)
        quote = HIGHLIGHTS.get(current["clause_id"], "\n".join(l["text"] for l in continuous))
        rects = quote_rects(first_lines, quote)
        box = fitz.Rect(rects[0])
        for rect in rects[1:]:
            box |= fitz.Rect(rect)
        clauses.append({"clause_id": current["clause_id"], "chapter": current["chapter"],
                        "page": segments[0]["page"], "text": text, "quote": quote,
                        "bbox": [round(v, 2) for v in box], "rects": rects,
                        "keywords": [k for k in KEYWORDS if normalize(k) in normalize(text)],
                        "related": RELATED.get(current["clause_id"], []),
                        "segments": segments, "cross_page": len(segments) > 1,
                        "numbering": current.get("numbering", "printed")})

    for n in range(start_page - 1, min(end_page, len(doc))):
        for line in body_lines(doc[n]):
            text = line["text"]
            chapter_match = re.match(r"^(\d{1,2})\s+([^\d].*)$", text) if line["bbox"][0] < 85 else None
            clause_match = re.match(r"^(\d{1,2}(?:\.\d+){1,2})\s+", text)
            table_match = re.match(r"^(\d{1,2})\s+", text) if chapter.startswith("2 ") and line["bbox"][0] < 120 else None
            clause_id = None
            numbering = "printed"
            if chapter_match:
                chapter = text
                section = text
                clause_id = chapter_match[1]
            elif clause_match:
                clause_id = clause_match[1]
                if clause_id.count(".") == 1:
                    section = text
            elif table_match:
                clause_id = "2." + table_match[1]
                numbering = "section_table_row"
            if clause_id:
                finish()
                current = {"clause_id": clause_id, "chapter": section or chapter, "lines": {}, "numbering": numbering}
            if current:
                current["lines"].setdefault(n + 1, []).append(line)
    finish()
    ids = [c["clause_id"] for c in clauses]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate clause ids; inspect PDF layout before publishing")
    (output / "clauses.json").write_text(json.dumps(clauses, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    page_map = {"version": "V3", "source_title": "第二十六届全国大学生机器人大赛女娲补天竞技赛规则V3",
                "revision_date": "2026-11-05", "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                "page_count": len(doc), "coordinate_system": "pymupdf-top-left-points",
                "note": "page 为从 1 开始的 PDF 物理页码；术语 2.n 对应第 2 节表格序号 n。解析仅为初稿，更新后须人工校对。",
                "pages": [{"physical_page": i + 1, "printed_page": str(i + 1) if i else None,
                           "width": round(page.rect.width, 2), "height": round(page.rect.height, 2),
                           "rotation": page.rotation} for i, page in enumerate(doc)]}
    (output / "page_map.json").write_text(json.dumps(page_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    destination = output / "rules.pdf"
    if pdf.resolve() != destination.resolve():
        shutil.copyfile(pdf, destination)
    doc.close()
    return clauses


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, default=DATA)
    parser.add_argument("--start-page", type=int, default=9)
    parser.add_argument("--end-page", type=int, default=29)
    args = parser.parse_args()
    clauses = extract(args.pdf, args.output, args.start_page, args.end_page)
    print(f"Extracted {len(clauses)} clauses. Review data, then run scripts/validate_clauses.py.")
