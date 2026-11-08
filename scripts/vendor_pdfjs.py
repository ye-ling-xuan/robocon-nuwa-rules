"""Copy a pinned pdfjs-dist npm package into the wheel; no runtime CDN use."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source", type=Path, help="directory of pdfjs-dist@5.6.205")
args = parser.parse_args()
meta = json.loads((args.source / "package.json").read_text(encoding="utf-8"))
if meta["version"] != "5.6.205":
    raise SystemExit("Expected pdfjs-dist@5.6.205; review integration before upgrading")
destination = ROOT / "server" / "ui" / "static" / "pdfjs"
destination.mkdir(parents=True, exist_ok=True)
for name in ("pdf.mjs", "pdf.worker.mjs"):
    shutil.copyfile(args.source / "build" / name, destination / name)
for folder in ("cmaps", "standard_fonts", "wasm"):
    shutil.copytree(args.source / folder, destination / folder, dirs_exist_ok=True)
for name in ("LICENSE", "NOTICE"):
    if (args.source / name).exists():
        shutil.copyfile(args.source / name, destination / name)
(destination / "version.json").write_text(json.dumps({"package": "pdfjs-dist", "version": meta["version"], "source": "https://www.npmjs.com/package/pdfjs-dist/v/5.6.205"}, indent=2) + "\n", encoding="utf-8")
print(f"Vendored PDF.js {meta['version']}, fonts, CMaps, WASM and licenses.")
