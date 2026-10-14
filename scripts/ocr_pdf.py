"""OCR a scanned PDF page by page with tesseract (vie) and cache the text.

Output: data/raw/ocr/<pdf-stem>/page-NNN.txt (plain text, tesseract's own line breaks)
        data/raw/ocr/<pdf-stem>/page-NNN.tsv (word-level boxes + confidences)
        data/raw/ocr/<pdf-stem>/meta.json    (source path, sha256, settings, per-page mean confidence)

Re-runnable: pages whose .txt already exists are skipped.
Needs: pdftoppm (poppler), tesseract >= 4 with vie.traineddata (tessdata_best) in $TESSDATA_PREFIX
(default ~/tessdata).

Usage: uv run python scripts/ocr_pdf.py data/raw/moj/5230-QD-BCA-C06.pdf [--pages 1-10] [--dpi 300] [--psm 4] [-j 4]
"""

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "data" / "raw" / "ocr"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def page_count(pdf: Path) -> int:
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    raise RuntimeError(f"no page count for {pdf}")


def parse_range(spec: str | None, n: int) -> list[int]:
    if not spec:
        return list(range(1, n + 1))
    pages: set[int] = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        pages.update(range(int(a), int(b or a) + 1))
    return sorted(p for p in pages if 1 <= p <= n)


def mean_conf(tsv_path: Path) -> float | None:
    confs = []
    with tsv_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if row.get("text", "").strip() and float(row["conf"]) >= 0:
                confs.append(float(row["conf"]))
    return round(sum(confs) / len(confs), 1) if confs else None


def ocr_page(pdf: Path, page: int, out_dir: Path, dpi: int, psm: int, env: dict) -> tuple[int, float | None]:
    stem = out_dir / f"page-{page:03d}"
    if stem.with_suffix(".txt").exists() and stem.with_suffix(".tsv").exists():
        return page, mean_conf(stem.with_suffix(".tsv"))
    with tempfile.TemporaryDirectory() as tmp:
        img_prefix = Path(tmp) / "p"
        subprocess.run(["pdftoppm", "-r", str(dpi), "-gray", "-png", "-singlefile",
                        "-f", str(page), "-l", str(page), str(pdf), str(img_prefix)], check=True)
        img = img_prefix.with_suffix(".png")
        base = ["tesseract", str(img), str(stem), "-l", "vie", "--oem", "1", "--psm", str(psm),
                "-c", "preserve_interword_spaces=1", "-c", "tessedit_create_txt=1", "-c", "tessedit_create_tsv=1"]
        # Single-threaded tesseract per page; parallelism comes from the pool.
        subprocess.run(base, check=True, env=env, capture_output=True)
    return page, mean_conf(stem.with_suffix(".tsv"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--pages", help="e.g. 1-5,9")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--psm", type=int, default=4, help="tesseract page segmentation mode (4 = single column of variable-size text)")
    ap.add_argument("-j", "--jobs", type=int, default=4)
    args = ap.parse_args()

    pdf = args.pdf.resolve()
    out_dir = OUT_ROOT / pdf.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, OMP_THREAD_LIMIT="1")
    env.setdefault("TESSDATA_PREFIX", str(Path.home() / "tessdata"))
    if not (Path(env["TESSDATA_PREFIX"]) / "vie.traineddata").exists():
        sys.exit(f"vie.traineddata not found in {env['TESSDATA_PREFIX']}")

    n = page_count(pdf)
    pages = parse_range(args.pages, n)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = dict(pool.map(lambda p: ocr_page(pdf, p, out_dir, args.dpi, args.psm, env), pages))

    meta_path = out_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {"page_conf": {}}
    meta.update({
        "source_pdf": str(pdf.relative_to(ROOT)) if pdf.is_relative_to(ROOT) else str(pdf),
        "source_sha256": sha256_file(pdf),
        "pages_total": n,
        "engine": subprocess.run(["tesseract", "--version"], capture_output=True, text=True).stdout.splitlines()[0],
        "lang": "vie (tessdata_best)",
        "dpi": args.dpi,
        "psm": args.psm,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    meta["page_conf"].update({f"{p:03d}": c for p, c in results.items()})
    meta["page_conf"] = dict(sorted(meta["page_conf"].items()))
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    low = {p: c for p, c in results.items() if c is not None and c < 80}
    print(f"{pdf.name}: {len(results)} pages OCR'd into {out_dir.relative_to(ROOT)}; "
          f"mean conf {round(sum(c for c in results.values() if c) / max(1, len(results)), 1)}; "
          f"pages < 80 conf: {sorted(low) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
