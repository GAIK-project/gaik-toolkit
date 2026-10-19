#!/usr/bin/env bash
# One-time setup for building and rendering decks.
# Installs: python-pptx, pillow, cairosvg, lxml, playwright (python); the default fonts
# (Montserrat, IBM Plex Sans/Mono, Source Serif 4) as TTF into ~/.fonts; Lucide icons.
# Needs: python3 (or python), pip, npm, fontconfig (fc-match, fc-cache), LibreOffice (soffice)
# and poppler (pdftoppm) on PATH.
set -uo pipefail
CACHE="$HOME/.cache/brief-to-slides"; mkdir -p "$CACHE" "$HOME/.fonts"
PY=python3; "$PY" -c "" 2>/dev/null || PY=python   # python3 may be missing or a Windows Store stub
"$PY" -c "import pptx, PIL, cairosvg, lxml" 2>/dev/null || "$PY" -m pip install --quiet --break-system-packages python-pptx pillow cairosvg lxml 2>/dev/null || "$PY" -m pip install --quiet python-pptx pillow cairosvg lxml
"$PY" -c "import playwright" 2>/dev/null || "$PY" -m pip install --quiet --break-system-packages playwright 2>/dev/null || "$PY" -m pip install --quiet playwright
"$PY" -m playwright install chromium >/dev/null 2>&1 || echo "CHROMIUM MISSING: check_deck.py --preview needs it (python -m playwright install chromium)"
cd "$CACHE"
[ -f package.json ] || npm init -y >/dev/null 2>&1
# Google Fonts as TTF via npm (GitHub raw downloads are often blocked in sandboxes)
npm install --silent @expo-google-fonts/montserrat @expo-google-fonts/ibm-plex-sans @expo-google-fonts/ibm-plex-mono @expo-google-fonts/source-serif-4 lucide-static >/dev/null 2>&1
find node_modules/@expo-google-fonts -name '*.ttf' -exec cp -n {} "$HOME/.fonts/" \; 2>/dev/null
if command -v fc-match >/dev/null; then
  fc-cache -f >/dev/null 2>&1
  for f in "Montserrat" "IBM Plex Sans" "IBM Plex Mono" "Source Serif 4"; do
    fam=$(fc-match -f '%{family}' "$f"); [[ "$fam" == *"$f"* ]] && echo "font ok: $f" || echo "FONT MISSING: $f (got $fam)"
  done
else
  echo "FONTCONFIG MISSING: fonts copied to ~/.fonts; dsl.py finds them there, but install them for LibreOffice/PowerPoint too"
fi
[ -d node_modules/lucide-static/icons ] && echo "icons ok: $CACHE/node_modules/lucide-static/icons" || echo "ICONS MISSING (npm install lucide-static failed)"
which soffice >/dev/null && echo "soffice ok" || echo "SOFFICE MISSING: install LibreOffice to render previews"
which pdftoppm >/dev/null && echo "pdftoppm ok" || echo "PDFTOPPM MISSING: install poppler-utils"
# For a template with other fonts: npm install @expo-google-fonts/<family-in-kebab-case> and copy its TTFs the same way.
