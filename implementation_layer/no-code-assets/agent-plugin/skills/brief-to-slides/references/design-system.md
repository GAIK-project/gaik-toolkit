# Design system (assets/template.pptx, default THEME in scripts/dsl.py)

Use this when no user template is supplied. With a user template, derive the same items from
`inspect_template.py` and write a THEME override; keep the structure of these rules.

## Canvas and chrome
- 16:9, 13.333 × 7.5 in. Margins: left 0.89 in, right edge 12.45 in.
- Master: full-width footer band, colour #0079C2, from y = 6.71 in to the bottom. No logos.
- Content slides: title in the layout's TITLE placeholder, Montserrat 32 pt bold #14213D, one line,
  at y 0.80 (title only, the default) or y 0.96 under an optional section label (kicker) at
  (0.89, 0.60), IBM Plex Sans 20 pt bold #A84A12, letter-spacing 1 pt (only if the user chose
  "Section label + title").
- Footer (inside the band): optional running footer text at (0.89, 6.88), IBM Plex Sans 12 pt
  #DCE3EE; slide number right-aligned at (11.56, 6.88).
- Logo (only if supplied): fitted inside its corner, aspect kept. Top right ≤ 1.9 × 0.62 in at
  y 0.12 (title box shortens to clear it); top left ≤ 0.42 in high; bottom corners ≤ 1.9 × 0.5 in,
  centred in the footer band (footer text / slide number move aside). Also on the title slide in
  the same corner. A dark logo on the blue band has poor contrast: ask for a light version or
  use a top corner.
- Body area: y 1.70 to 6.32 in. Source line: (0.89, 6.40), IBM Plex Sans 12 pt #5B6472, one line,
  starting "Source:" / "Sources:". Page number: right-aligned box (11.56, 6.88), 12 pt #DCE3EE.
- Title slide: background #0079C2 (theme accent1), master graphics hidden. Kicker 20 pt bold
  #F2B27A at y 1.38; title Source Serif 4 48 pt bold #F7F5F0 at y 1.76; subtitle IBM Plex Sans
  28 pt #DCE3EE at y 2.78; opening-question box #1D2D50 with a 0.06 in orange left bar below the
  subtitle (only if the user gave a question); presenter name (IBM Plex Sans 20 pt bold #F7F5F0)
  and affiliation (16 pt #DCE3EE) bottom-left above y 6.95 (only if given). Nothing else on the
  title slide: no illustrations, mock-ups, cards or icons. Use `cover()`.

## Colour roles
| Role | Hex |
|---|---|
| Text, dark panels, table headers | #14213D (navy), #1D2D50 (navy 2) |
| Accent: bars, arrows, numbers | #E07A2E (orange) |
| Kicker, warning labels, "you check" | #A84A12 (burnt orange) |
| Secondary accent: labels, links, data bars | #2F6DB5 (blue) |
| Brand band, title background | #0079C2 |
| Card fill + border | #FFFDF9 + #E2DED5 |
| Tints | #E8EEF6 (blue), #D3DFEE (blue 2), #FBE3CF (orange), #FFF6EC (warm), #F2C9A0 (orange mid) |
| Secondary text | #3F4A5A, #5B6472 |
| Text on dark | #F7F5F0, #DCE3EE, #F2B27A; "pass"/positive on dark #99C879 |

Colour never carries meaning alone: risk/effort chips say "Low/Med/High", test lines say
PASS/FAIL, flagged items say why.

## Type scale (pt)
48 cover title · 32 slide title · 28 cover subtitle · 20 kicker / key phrases (17–20) ·
15–16 card titles · 13–14 body, table cells, notes in cards · 12 labels, source line, page
number (minimum). Fonts: Montserrat (headings, body), IBM Plex Sans (kickers, labels, captions,
chips, source lines), IBM Plex Mono (code, file trees, IDs), Source Serif 4 (cover title only).

## Shapes and recurring motifs
- Cards: rounded rectangles, radius ≈ 0.07–0.1 in, cream fill with 1 pt #E2DED5 border, or tint
  fills without border; dark navy cards for emphasis (light text).
- Key phrase: 2.5 pt orange vertical bar at the left, text 0.21 in to the right (`KP`/`KPS`).
- Takeaway banner: full-width navy bar at the bottom of the body area with an icon and one
  bold sentence (`banner`).
- Labels: upper-case IBM Plex Sans bold 12–14 pt, grey or blue (`label`).
- Arrows: small orange block arrows between steps; connectors blue for read/info flows and
  orange for actions/writes; dashed orange for loops ("iterate").
- Icons: Lucide line icons, 2 px stroke, blue on light, peach on dark, 0.32–0.45 in.
  No robots.
- Tables and matrices are drawn with shapes (not native tables) so PPTX and HTML match.
- No label words on slides ("illustrative", "mock-up", "fictional", "synthetic data"):
  disclosures belong in the speaker notes. `check_deck.py` fails on them.
