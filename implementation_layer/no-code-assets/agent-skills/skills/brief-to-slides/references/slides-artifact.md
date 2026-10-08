# Optional: the same deck as a Claude Slides deck

Use when the user asks for a Slides deck or the session started from the Slides output type.
Follow the Slides type's own instructions (returned when the deck is created); this file only
covers how this skill's spec maps onto it.

1. Create the deck from the Slides type with a title (open after first write).
2. Upload every local image the spec uses (logos, photos) as assets of that deck; save
   `{basename: "/_blob/…"}` to `blobs.json`. Icons are inline SVG and need no upload.
3. `python build.py spec.py --out deck.pptx --slides-dir DIR --blobs blobs.json`
   writes `DIR/project/deck.json` (title, order, sections from `SECTIONS`, Google Fonts faces)
   and one `DIR/project/slides/<id>.html` per slide.
4. Publish `project/deck.json` + the cover first, then the remaining slide files in batches,
   with `root` = DIR.

Mapping used by `render_html.py`: 1 in = 144 px, 1 pt = 2 px (so 12 pt is the 24 px minimum),
every element absolutely positioned; text boxes are flex columns of `<p>` with
`line-height = lh × font line factor`, so wrapping matches the PPTX. Rectangles are painted
divs, block arrows `x-shape`, lines `x-connector`, icons inline SVG, mono text uses
non-breaking spaces. Notes go in a final `<aside>` (≤ 4000 characters; build.py stops if
longer). The footer band, kicker, title (`h1` on the cover, `h2` elsewhere), source line and
page number are drawn on each slide from THEME.

Slide masters cannot be carried into a Slides deck: tell the user the .pptx is the version
that keeps the template's masters.
