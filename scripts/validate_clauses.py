"""Validate every citation against the shipped PDF, including bounding boxes."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pymupdf as fitz

try:
    from .parse_pdf import DATA, body_lines, normalize, quote_rects
except ImportError:
    from parse_pdf import DATA, body_lines, normalize, quote_rects


def validate(data_dir: Path = DATA) -> list[str]:
    errors = []
    clauses = json.loads((data_dir / "clauses.json").read_text(encoding="utf-8"))
    meta = json.loads((data_dir / "page_map.json").read_text(encoding="utf-8"))
    pdf = data_dir / "rules.pdf"
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != meta["pdf_sha256"]:
        errors.append("PDF hash differs from page_map.json; rebuild the dataset")
    with fitz.open(pdf) as doc:
        if len(doc) != meta["page_count"]:
            errors.append("Page count mismatch")
        ids = {c["clause_id"] for c in clauses}
        if len(ids) != len(clauses):
            errors.append("Duplicate clause ids")
        for c in clauses:
            label = c["clause_id"]
            if not re.fullmatch(r"\d+(?:\.\d+){0,2}", label):
                errors.append(f"Invalid clause id {label}")
            if c["page"] != c["segments"][0]["page"]:
                errors.append(f"{label}: main page differs from first segment")
            for segment in [c, *c["segments"]]:
                p = segment["page"]
                if not isinstance(p, int) or not 1 <= p <= len(doc):
                    errors.append(f"{label}: invalid physical page {p}")
                    continue
                page = doc[p - 1]
                lines = body_lines(page)
                text = normalize("".join(l["text"] for l in lines))
                if not segment["quote"] or normalize(segment["quote"]) not in text:
                    errors.append(f"{label} P{p}: quote is absent from PDF")
                    continue
                expected = quote_rects(lines, segment["quote"])
                if segment.get("rects") is not None and expected != segment["rects"]:
                    errors.append(f"{label} P{p}: highlight coordinates differ from PDF text")
                for box in ([segment["bbox"]] if segment.get("bbox") else []) + (segment.get("rects") or []):
                    x0, y0, x1, y1 = box
                    if not (0 <= x0 < x1 <= page.rect.width + .1 and 0 <= y0 < y1 <= page.rect.height + .1):
                        errors.append(f"{label} P{p}: bbox outside page")
            for related in c["related"]:
                if related not in ids:
                    errors.append(f"{label}: missing related clause {related}")
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    args = parser.parse_args()
    issues = validate(args.data)
    for issue in issues:
        print(issue)
    if issues:
        raise SystemExit(1)
    print("OK: all clause IDs, physical pages, quotes, PDF hash and highlight coordinates validated.")
