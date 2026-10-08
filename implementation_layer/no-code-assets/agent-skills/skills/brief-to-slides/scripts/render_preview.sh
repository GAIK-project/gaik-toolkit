#!/usr/bin/env bash
# Render a .pptx to PNGs with LibreOffice and make a contact sheet for visual review.
#   render_preview.sh deck.pptx OUTDIR [DPI]
# Then view OUTDIR/sheet.png (overview) and OUTDIR/slide-NN.png (detail) with the Read tool.
set -euo pipefail
PPTX="$1"; OUT="${2:-preview}"; DPI="${3:-72}"
mkdir -p "$OUT"; rm -f "$OUT"/slide-*.png
soffice --headless --convert-to pdf --outdir "$OUT" "$PPTX" >/dev/null 2>&1
PDF="$OUT/$(basename "${PPTX%.*}").pdf"
pdftoppm -r "$DPI" -png "$PDF" "$OUT/slide"
python3 - "$OUT" << 'PY'
import sys, glob, re
from PIL import Image
out = sys.argv[1]
fs = sorted(glob.glob(f'{out}/slide-*.png'), key=lambda f: int(re.findall(r'(\d+)\.png$', f)[0]))
im = Image.open(fs[0]); w, h = im.size; cols = 3; rows = (len(fs) + cols - 1) // cols
sheet = Image.new('RGB', (cols * (w + 8), rows * (h + 8)), 'black')
for i, f in enumerate(fs):
    sheet.paste(Image.open(f).convert('RGB'), ((i % cols) * (w + 8), (i // cols) * (h + 8)))
sheet.thumbnail((2600, 2600 * rows))
sheet.save(f'{out}/sheet.png'); print(len(fs), 'slides ->', f'{out}/sheet.png')
PY
