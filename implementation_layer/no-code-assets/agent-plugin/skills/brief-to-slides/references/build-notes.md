# Build notes and pitfalls

## Environment
- Run `scripts/setup_env.sh` once. It installs python-pptx, Pillow, cairosvg, lxml, Playwright,
  the default fonts (as TTF via npm `@expo-google-fonts/*`, because raw GitHub/Google Fonts
  downloads are often blocked in sandboxes) and Lucide icons (`lucide-static`).
- Measurements and renders are only right when the deck's fonts are installed locally. If
  `dsl.py` warns that a font is missing, install it before judging layout.
- Never name a script after a Python module (e.g. `inspect.py` breaks `import pptx`).

## Template handling (render_pptx.py does this)
- Work on a copy. Delete every slide: drop each `sldId` relationship, remove it from `sldIdLst`,
  then drop any remaining `/slide` relationships (orphan slides). Unreferenced parts, old notes
  and media disappear on save.
- Use the template layout named in THEME (`layout`) and its TITLE placeholder; delete the other
  placeholders on each slide.
- Title slide: background from THEME (`title_bg`, scheme colour or hex) and
  `showMasterSp="0"` when the template hides master graphics on its cover.
- Notes: some templates have a notes master without placeholders, so `notes_text_frame` is
  None. The renderer copies the sldImg/body placeholders from an existing notes slide of the
  template, or inserts a minimal body placeholder.
- Every added shape has its `p:style` removed (no theme shadows/outlines). Text boxes: zero
  insets, `noAutofit`, explicit latin/ea/cs fonts.
- Removing a logo from a template: delete the picture shape AND drop the now-unused image
  relationship from the master/layout, or the image stays in the file.

## Text fitting (the most common defect)
- Size boxes with `text_h()` (real font metrics, word wrapping) instead of guessing.
- PowerPoint "single" spacing = font natural line height (Montserrat 1.22 em, IBM Plex 1.30,
  Source Serif 4 1.37). A one-line label at 20 pt IBM Plex needs ≥ 0.37 in.
- Keep at least 0.05 in slack; labels that must stay on one line: widen the box or shorten text.
- Do not rely on autofit; never go below 12 pt.

## Verify
1. `python build.py spec.py --template T --out deck.pptx --preview preview.html`
2. `python check_deck.py --pptx deck.pptx --minutes N --preview preview.html --forbid "old,text"`
   (overflow, mid-word wrapping, timings, notes, leftover text, hidden slides).
3. `bash render_preview.sh deck.pptx out 72` and look at `out/sheet.png` and individual slides.
   LibreOffice renders close to PowerPoint; tiny line-break differences are possible, so keep
   slack in boxes.
4. Fix, rebuild, re-check until clean. Typical fixes: widen chips, shorten labels, reduce
   phrases, move detail to notes, give two-line titles more height.
