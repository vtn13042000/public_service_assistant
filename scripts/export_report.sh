#!/usr/bin/env bash
# Export the technical report (Markdown) to .docx and .pdf with local tools only (no pandoc on this host):
#   Markdown → HTML with markdown-it-py (already in the project environment; tables enabled)
#   HTML → .docx and .pdf with LibreOffice headless (soffice).
# Usage: scripts/export_report.sh [docs/09_report/BAO-CAO-KY-THUAT.md]
# Outputs next to the input: <name>.html (intermediate), <name>.docx, <name>.pdf. Mermaid blocks stay as code (no local renderer).
set -euo pipefail
SRC="${1:-docs/09_report/BAO-CAO-KY-THUAT.md}"
DIR="$(dirname "$SRC")"; NAME="$(basename "$SRC" .md)"
HTML="$DIR/$NAME.html"
uv run python - "$SRC" "$HTML" <<'PY'
import sys, re, html
from markdown_it import MarkdownIt
src, out = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8").read()
md = MarkdownIt("commonmark", {"html": False}).enable("table")
body = md.render(text)
body = re.sub(r"</?t(head|body)>\n?", "", body)
body = re.sub(r"<tr>\n(<th)", '<tr bgcolor="#e8e8e8">\n\\1', body)  # header row shaded; <th> → bold <td> (LibreOffice adds a blank row under <th>)
body = re.sub(r"<th([^>]*)>(.*?)</th>", r"<td\1><b>\2</b></td>", body)
def _cols(m):  # fixed column widths: LibreOffice otherwise squeezes some columns until numbers wrap
    t = m.group(0)
    first = re.search(r"<tr[^>]*>(.*?)</tr>", t, re.S)
    n = len(re.findall(r"<t[hd][ >]", first.group(1))) if first else 0
    if n < 2:
        return t
    w0 = 22 if n >= 5 else 30
    rest = (100 - w0) / (n - 1)
    cg = "<colgroup>" + f'<col width="{w0}%">' + "".join(f'<col width="{rest:.1f}%">' for _ in range(n - 1)) + "</colgroup>"
    return t.replace("<table>", "<table>" + cg, 1)
body = re.sub(r"<table>.*?</table>", _cols, body, flags=re.S)
body = body.replace("<table>", '<table border="1" cellspacing="0" cellpadding="1" width="100%">')
body = body.replace("<p>[[pagebreak]]</p>", '<p style="page-break-before: always"></p>')  # a line "[[pagebreak]]" in the Markdown
def _img(m):  # embed local images (LibreOffice would only link them), downscaled to 1600 px, at the full text width
    import base64, io, os
    from PIL import Image
    path = os.path.join(os.path.dirname(src), m.group(1))
    if not os.path.exists(path):
        return m.group(0)
    im = Image.open(path).convert("RGB")
    if im.width > 1600:
        im = im.resize((1600, round(im.height * 1600 / im.width)), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=88)
    return f'<img src="data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}" width="500"{m.group(2)}'
body = re.sub(r'<img src="([^":]+)"([^>]*>)', _img, body)
title = html.escape(next((l[2:] for l in text.splitlines() if l.startswith("# ")), "Report"))
css = """
body { font-family: 'DejaVu Sans', 'Noto Sans', 'Liberation Sans', sans-serif; font-size: 10.5pt; line-height: 1.35; }
h1 { font-size: 18pt; } h2 { font-size: 14pt; margin-top: 18pt; } h3 { font-size: 12pt; }
table { border-collapse: collapse; font-size: 9pt; margin: 6pt 0; }
th { background: #e8e8e8; } th, td { border: 1px solid #888; padding: 1pt 3pt; vertical-align: top; }
code, pre { font-family: 'DejaVu Sans Mono', 'Liberation Mono', monospace; font-size: 8.5pt; }
pre { background: #f4f4f4; padding: 6pt; white-space: pre-wrap; }
"""
open(out, "w", encoding="utf-8").write(
    f'<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>{title}</title><style>{css}</style></head><body>{body}</body></html>')
print("html:", out)
PY
soffice --headless --convert-to "docx:MS Word 2007 XML" --outdir "$DIR" "$HTML" >/dev/null 2>&1
# fix table column widths in the .docx (LibreOffice's HTML import ignores <col width>): widths follow content length, autofit off
uv run python - "$DIR/$NAME.docx" <<'PY2'
import sys
from docx import Document
from docx.shared import Emu
doc = Document(sys.argv[1])
sec = doc.sections[0]
usable = sec.page_width - sec.left_margin - sec.right_margin
for t in doc.tables:
    n = len(t.columns)
    if n < 2:
        continue
    t.autofit = False
    # width ∝ sqrt(mean text length of the column's cells), floor 6% of the line
    lens = [sum(len(r.cells[i].text) for r in t.rows) / len(t.rows) for i in range(n)]
    wts = [max(3.0, L) ** 0.5 for L in lens]
    widths = [max(int(usable * 0.06), int(usable * w / sum(wts))) for w in wts]
    scale = usable / sum(widths)
    widths = [int(w * scale) for w in widths]
    for row in t.rows:
        for i, cell in enumerate(row.cells[:n]):
            cell.width = Emu(widths[i])
    for i, col in enumerate(t.columns):
        col.width = Emu(widths[i])
    for row in t.rows:  # no paragraph spacing inside cells: LibreOffice's default doubles every row's height
        for cell in row.cells:
            for par in cell.paragraphs:
                par.paragraph_format.space_before = Emu(0)
                par.paragraph_format.space_after = Emu(0)
doc.save(sys.argv[1])
PY2
soffice --headless --convert-to pdf --outdir "$DIR" "$DIR/$NAME.docx" >/dev/null 2>&1
ls -l "$DIR/$NAME.docx" "$DIR/$NAME.pdf"
