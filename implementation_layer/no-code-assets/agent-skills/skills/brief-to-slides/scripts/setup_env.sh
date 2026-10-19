#!/usr/bin/env bash
# One-time setup for building and rendering decks.
# Installs: python-pptx, pillow, cairosvg, lxml, playwright (python); the default fonts
# (Montserrat, IBM Plex Sans/Mono, Source Serif 4) as TTF into ~/.fonts; Lucide icons.
# Needs: python3, pip, npm, LibreOffice (soffice) and poppler (pdftoppm) on PATH.
set -uo pipefail
CACHE="$HOME/.cache/brief-to-slides"; mkdir -p "$CACHE" "$HOME/.fonts"
PY_PKGS="python-pptx==1.0.2 pillow==12.3.0 cairosvg==2.9.1 lxml==6.1.3"
python3 -c "import pptx, PIL, cairosvg, lxml" 2>/dev/null || pip install --quiet --break-system-packages $PY_PKGS 2>/dev/null || pip install --quiet $PY_PKGS
python3 -c "import playwright" 2>/dev/null || { pip install --quiet --break-system-packages playwright==1.64.0 2>/dev/null || pip install --quiet playwright==1.64.0; python3 -m playwright install chromium >/dev/null 2>&1 || true; }
cd "$CACHE"
[ -f package.json ] || npm init -y >/dev/null 2>&1
# Google Fonts as TTF via npm (GitHub raw downloads are often blocked in sandboxes)
npm install --silent @expo-google-fonts/montserrat@0.4.2 @expo-google-fonts/ibm-plex-sans@0.4.1 @expo-google-fonts/ibm-plex-mono@0.4.1 @expo-google-fonts/source-serif-4@0.4.2 lucide-static@1.59.0 >/dev/null 2>&1
find node_modules/@expo-google-fonts -name '*.ttf' -exec cp -n {} "$HOME/.fonts/" \; 2>/dev/null
fc-cache -f >/dev/null 2>&1
for f in "Montserrat" "IBM Plex Sans" "IBM Plex Mono" "Source Serif 4"; do
  fam=$(fc-match -f '%{family}' "$f"); [[ "$fam" == *"$f"* ]] && echo "font ok: $f" || echo "FONT MISSING: $f (got $fam)"
done
[ -d node_modules/lucide-static/icons ] && echo "icons ok: $CACHE/node_modules/lucide-static/icons" || echo "ICONS MISSING (npm install lucide-static failed)"
which soffice >/dev/null && echo "soffice ok" || echo "SOFFICE MISSING: install LibreOffice to render previews"
which pdftoppm >/dev/null && echo "pdftoppm ok" || echo "PDFTOPPM MISSING: install poppler-utils"
# For a template with other fonts: npm install @expo-google-fonts/<family-in-kebab-case> and copy its TTFs the same way.
