"""Layout DSL shared by render_pptx.py and render_html.py.

A deck spec is a Python module that defines:
    SLIDES = [dict(id=..., kind='title'|'content', kicker=..., title=..., els=[...],
                   minutes=N, notes='...', source='...' (optional)), ...]
    THEME  = {...}   (optional overrides of DEFAULT_THEME below)

Geometry is in inches on a 13.333 x 7.5 in (16:9) canvas. Sizes are in points.
Text is measured with the real fonts (via fontconfig), so heights you compute with
text_h() match what LibreOffice/PowerPoint and the browser render.
"""
import os
import subprocess
from PIL import ImageFont

# ---------------------------------------------------------------- palette / fonts
# Default design = assets/template.pptx (see references/design-system.md)
NAVY = '14213D'; NAVY2 = '1D2D50'; ORANGE = 'E07A2E'; BURNT = 'A84A12'; BLUE = '2F6DB5'
BRAND = '0079C2'; CREAM = 'FFFDF9'; CREAMLINE = 'E2DED5'; BLUETINT = 'E8EEF6'; ORTINT = 'FBE3CF'
GREY = '5B6472'; GREY2 = '3F4A5A'; LIGHT = 'F7F5F0'; PALEBLUE = 'DCE3EE'; PEACH = 'F2B27A'
BLUE2 = 'D3DFEE'; WARM = 'FFF6EC'; ORMID = 'F2C9A0'; BLUELINE = 'C9D2DF'; GREEN = '99C879'; WHITE = 'FFFFFF'

H = 'Montserrat'        # headings + most body text
B = 'IBM Plex Sans'     # kickers, labels, captions, source lines
M = 'IBM Plex Mono'     # code, file trees, IDs
S = 'Source Serif 4'    # title-slide title only

DEFAULT_THEME = dict(
    layout='Title and body',          # slide layout used for every slide
    content_bg=None,                   # None = inherit master (white); else hex
    title_bg='accent1',                # title slide background: theme colour name or hex
    title_hide_master=True,            # hide master graphics (footer band) on the title slide
    # ---- intake answers (SKILL.md §1b); defaults = what happens when the user is not asked ----
    show_kicker=False,                 # small section label above each slide title ("OPENING" ...)
    footer_text=None,                  # running footer text on content slides, e.g. 'Course X · Autumn 2026'
    page_numbers=True,                 # slide numbers on content slides
    logo=None,                         # dict(path='logo.png', position='top-right'|'top-left'|'bottom-right'|'bottom-left', alt='…')
    logo_on_cover=True,                # also show the logo on the title slide (same corner)
    # ---- chrome geometry (x, y, w, h) ----
    kicker=dict(box=(0.89, 0.60, 10.0, 0.38), size=20, font=B, color=BURNT, spc=100),
    title=dict(box=(0.89, 0.96, 10.05, 0.55), size=32, font=H, color=NAVY),
    title_no_kicker_y=0.80,            # title y when show_kicker is False
    cover_title=dict(box=(0.89, 1.76, 7.3, 0.95), size=48, font=S, color=LIGHT),
    source=dict(box=(0.89, 6.40, 11.56, 0.28), size=12, font=B, color=GREY),
    page_number=dict(box=(11.56, 6.88, 0.89, 0.26), size=12, font=B, color=PALEBLUE),
    footer=dict(box=(0.89, 6.88, 8.5, 0.26), size=12, font=B, color=PALEBLUE),
    footer_band=dict(box=(0, 6.711, 13.333, 0.789), color=BRAND),   # drawn by the master in PPTX; drawn explicitly in HTML
    # max logo boxes per corner (w, h); the logo keeps its aspect ratio inside
    logo_max=dict(top=(1.9, 0.62), bottom=(1.9, 0.5)),
    content_area=(0.89, 1.70, 12.45, 6.32),   # left, top, right, bottom usable for slide body
)


def resolve_theme(theme=None):
    th = dict(DEFAULT_THEME)
    th.update(theme or {})
    return th


def _logo_box(th, cover=False):
    """(x, y, w, h) of the logo for this slide, fitted to its corner."""
    lg = th.get('logo')
    if not lg:
        return None
    from PIL import Image
    iw, ih = Image.open(lg['path']).size
    pos = lg.get('position', 'top-right')
    vert, horiz = pos.split('-')
    mw, mh = th['logo_max']['top' if vert == 'top' else 'bottom']
    if pos == 'top-left' and not cover:
        mh = min(mh, 0.42)            # stays above the section label / title, which keep their places
    w = mw; h = w * ih / iw
    if h > mh:
        h = mh; w = h * iw / ih
    x = 0.89 if horiz == 'left' else 12.45 - w
    if vert == 'top':
        y = 0.12
    else:
        band_y = th['footer_band']['box'][1] if th.get('footer_band') else 6.711
        y = (6.95 - h if cover else band_y + (7.5 - band_y - h) / 2)
    return (x, y, w, h)


def chrome(sd, n, theme=None):
    """Recurring elements for one slide (everything except the title): section label, logo,
    footer text, slide number, source line. Shared by the PPTX and HTML renderers."""
    th = resolve_theme(theme)
    cover = sd['kind'] == 'title'
    els = []
    lb = _logo_box(th, cover)
    if lb and (not cover or th['logo_on_cover']):
        els.append(IMG(th['logo']['path'], *lb, th['logo'].get('alt', 'Logo')))
    if not cover and th['show_kicker'] and sd.get('kicker'):
        k = th['kicker']; x, y, w, h = k['box']
        if lb and lb[1] < 1.0 and lb[0] > 6:   # top-right logo: keep the label clear of it
            w = min(w, lb[0] - 0.25 - x)
        els.append(T(x, y, w, h, sd['kicker'], size=k['size'], font=k['font'], bold=True, color=k['color'], spc=k['spc']))
    if sd.get('source'):
        s_ = th['source']; els.append(T(*s_['box'], sd['source'], size=s_['size'], font=s_['font'], color=s_['color']))
    if not cover:
        bottom_logo = lb and lb[1] > 6.0
        if th['footer_text']:
            f = th['footer']; x, y, w, h = f['box']
            if bottom_logo and lb[0] < 2:     # bottom-left logo: footer text starts after it
                x = lb[0] + lb[2] + 0.3
            els.append(T(x, y, w, h, th['footer_text'], size=f['size'], font=f['font'], color=f['color']))
        if th['page_numbers']:
            pn = th['page_number']; x, y, w, h = pn['box']
            if bottom_logo and lb[0] > 6:     # bottom-right logo: number moves left of it
                x = lb[0] - w - 0.25
            els.append(T(x, y, w, h, str(n), size=pn['size'], font=pn['font'], color=pn['color'], align='r'))
    return els


def title_box(sd, theme=None):
    """Title box for a content slide, honouring show_kicker and a top logo."""
    th = resolve_theme(theme)
    x, y, w, h = th['title']['box']
    if not th['show_kicker']:
        y = th['title_no_kicker_y']
    lb = _logo_box(th, False)
    if lb and lb[1] < 1.0:
        if lb[0] > 6:                      # top-right logo: shorten the title box
            w = min(w, lb[0] - 0.25 - x)
        else:                              # top-left logo (max 0.42 in high): title stays below it
            y = max(y, lb[1] + lb[3] + 0.2)
    return (x, y, w, h)


# ---------------------------------------------------------------- elements
def R(x, y, w, h, fill=None, line=None, lw=1.0, r=0.07, dash=False):
    """Rectangle; r = corner radius in inches (0 = square)."""
    return dict(t='rect', x=x, y=y, w=w, h=h, fill=fill, line=line, lw=lw, r=r, dash=dash)


def E(x, y, w, h, fill=None, line=None, lw=1.0):
    return dict(t='ellipse', x=x, y=y, w=w, h=h, fill=fill, line=line, lw=lw)


def P(runs, **kw):
    """Paragraph. runs: str or list of str / (text, style). style keys: bold italic color font
    underline link spc. Paragraph kw may override size font bold italic color align lh gap spc."""
    if isinstance(runs, str):
        runs = [(runs, {})]
    runs = [(r, {}) if isinstance(r, str) else r for r in runs]
    return dict(runs=runs, **kw)


def T(x, y, w, h, paras, size=16, color=NAVY, font=H, bold=False, italic=False,
      align='l', valign='t', lh=1.0, gap=0.0, spc=0):
    """Text box. align l|c|r, valign t|m|b, lh = line spacing multiple (1.0 = single),
    gap = space between paragraphs (in), spc = letter spacing (1/100 pt)."""
    if isinstance(paras, (str, dict)):
        paras = [paras]
    paras = [P(p) if isinstance(p, str) else p for p in paras]
    return dict(t='text', x=x, y=y, w=w, h=h, paras=paras, size=size, color=color, font=font,
                bold=bold, italic=italic, align=align, valign=valign, lh=lh, gap=gap, spc=spc)


def BAR(x, y, h, color=ORANGE, lw=2.5):
    """Vertical accent bar (key-phrase marker)."""
    return dict(t='line', x1=x, y1=y, x2=x, y2=y + h, color=color, lw=lw, head=None, dash=False)


def LN(x1, y1, x2, y2, color=ORANGE, lw=2.0, head='end', dash=False):
    """Straight line/connector. head: None | 'end' | 'both'."""
    return dict(t='line', x1=x1, y1=y1, x2=x2, y2=y2, color=color, lw=lw, head=head, dash=dash)


def ARW(x, y, w, h, d='r', color=ORANGE):
    """Block arrow, d = r|l|u|d. Keep near 1:1 to 2:1."""
    return dict(t='arrow', x=x, y=y, w=w, h=h, d=d, color=color)


def IMG(path, x, y, w, h, alt=''):
    return dict(t='img', path=path, x=x, y=y, w=w, h=h, alt=alt)


def ICON(name, x, y, s=0.36, color=BLUE, sw=2.0):
    """Lucide icon by name (https://lucide.dev/icons). Avoid robot/bot icons."""
    return dict(t='icon', name=name, x=x, y=y, s=s, color=color, sw=sw)


# ---------------------------------------------------------------- measurement
_cache, _path_cache = {}, {}


def font_file(font, bold=False, italic=False):
    key = (font, bool(bold), bool(italic))
    if key not in _path_cache:
        pat = font + (':weight=bold' if bold else '') + (':slant=italic' if italic else '')
        p = subprocess.run(['fc-match', '-f', '%{file}', pat], capture_output=True, text=True).stdout.strip()
        fam = subprocess.run(['fc-match', '-f', '%{family}', pat], capture_output=True, text=True).stdout
        if font.lower() not in fam.lower():
            print(f'WARNING: font "{font}" not installed (fc-match gave {fam!r}); run setup_env.sh. Measurements are approximate.')
        _path_cache[key] = p
    return _path_cache[key]


def _font(font, bold, italic):
    k = (font, bool(bold), bool(italic))
    if k not in _cache:
        _cache[k] = ImageFont.truetype(font_file(font, bold, italic), 100)
    return _cache[k]


def line_factor(font):
    """Natural line height / em (hhea ascent+descent). PowerPoint 'single' spacing uses this."""
    f = _font(font, False, False)
    a, d = f.getmetrics()
    return round((a + d) / 100, 3)


def text_w(text, size, font=H, bold=False, italic=False):
    return _font(font, bold, italic).getlength(text) * size / 100 / 72


def est_lines(text, w, size, font=H, bold=False, italic=False):
    f = _font(font, bold, italic)
    maxw = w * 72 * 100 / size * 0.99
    lines = 0
    for para in text.split('\n'):
        cur = ''; lines += 1
        for wd in para.split():
            t = (cur + ' ' + wd) if cur else wd
            if f.getlength(t) > maxw and cur:
                lines += 1; cur = wd
            else:
                cur = t
    return lines


def text_h(text, w, size, font=H, lh=1.0, bold=False, italic=False):
    """Height in inches the text needs in a box of width w."""
    return est_lines(text, w, size, font, bold, italic) * size * lh * line_factor(font) / 72


# ---------------------------------------------------------------- pattern helpers
def KP(x, y, w, text, size=20, font=H, color=NAVY, bold=False, barcolor=ORANGE):
    """Key phrase: accent bar + text. Returns (elements, height)."""
    h = text_h(text, w - 0.21, size, font, 1.0, bold) + 0.02
    return [BAR(x + 0.02, y, h + 0.02, barcolor),
            T(x + 0.21, y + 0.01, w - 0.21, h, text, size=size, font=font, color=color, bold=bold)], h


def KPS(x, y, w, items, size=20, gap=0.28, **kw):
    """Stack of key phrases. Returns (elements, next_y)."""
    out = []
    for it in items:
        els, h = KP(x, y, w, it, size=size, **kw)
        out += els
        y += h + gap
    return out, y


def chip(x, y, w, h, text, fill=BLUETINT, color=NAVY, size=14, font=B, bold=False, line=None, align='c', r=0.06):
    """Pill/label with centred text."""
    return [R(x, y, w, h, fill, line, r=r),
            T(x + 0.08, y, w - 0.16, h, text, size=size, font=font, color=color, bold=bold, align=align, valign='m')]


def label(x, y, w, text, color=GREY, size=14):
    """Upper-case section label (e.g. 'WHAT YOU MUST CHECK')."""
    return T(x, y, w, 0.34, text.upper(), size=size, font=B, bold=True, color=color, spc=60)


def banner(text, y=5.75, h=0.5, icon=None, fill=NAVY, color=LIGHT, size=16, x=0.89, w=11.56):
    """Full-width takeaway banner at the bottom of the content area."""
    els = [R(x, y, w, h, fill, r=0.08)]
    tx = x + 0.2
    if icon:
        els.append(ICON(icon, x + 0.18, y + (h - 0.34) / 2, 0.34, PEACH))
        tx = x + 0.68
    els.append(T(tx, y, w - (tx - x) - 0.2, h, text, size=size, font=B, bold=True, color=color, valign='m'))
    return els


def card(x, y, w, h, title, body, fill=CREAM, line=CREAMLINE, icon=None, title_size=16, body_size=14,
         title_color=NAVY, body_color=GREY2):
    """Card with optional icon, bold title and body text (body may be str or list of P)."""
    els = [R(x, y, w, h, fill, line, r=0.08)]
    tx = x + 0.18
    if icon:
        els.append(ICON(icon, x + 0.18, y + 0.16, 0.4, BLUE if fill != NAVY else PEACH))
        tx = x + 0.7
    th = text_h(title, x + w - 0.18 - tx, title_size, H, bold=True) + 0.04
    els.append(T(tx, y + 0.14, x + w - 0.18 - tx, max(th, 0.42), title, size=title_size, bold=True, color=title_color,
                 valign='m'))
    by = y + 0.14 + max(th, 0.42) + 0.08
    els.append(T(x + 0.18, by, w - 0.36, y + h - by - 0.1, body, size=body_size, color=body_color))
    return els


def step_row(steps, y=1.75, h=1.4, x0=0.89, total_w=11.56, gap=0.24, dark=(), size=15):
    """Horizontal process: steps = [(number, title, desc)], arrows between. dark = indices drawn dark."""
    n = len(steps); w = (total_w - gap * (n - 1)) / n
    els = []
    for i, (num, t, d) in enumerate(steps):
        x = x0 + i * (w + gap)
        dk = i in dark
        els += [R(x, y, w, h, NAVY if dk else BLUETINT, r=0.08),
                T(x + 0.15, y + 0.1, w - 0.3, 0.62, [P([(f'{num}  ', {'color': PEACH if dk else BURNT}), (t, {})])],
                  size=size, bold=True, color=LIGHT if dk else NAVY),
                T(x + 0.15, y + 0.72, w - 0.3, h - 0.8, d, size=13, font=B, color=PALEBLUE if dk else GREY2)]
        if i < n - 1:
            els.append(ARW(x + w + 0.01, y + h / 2 - 0.1, gap - 0.02, 0.2, 'r'))
    return els


def matrix(cols, row_labels, cells, y=1.70, x0=0.89, label_w=1.5, right=12.45, head_h=0.6, row_h=0.78,
           gap=0.08, size=13, highlight_last=True):
    """Feature matrix: column headers (dark), row labels (tinted), cells (cream).
    cells[r][c] text. Last row label tinted orange (e.g. 'You check') when highlight_last."""
    n = len(cols); cw = (right - x0 - label_w - gap * n) / n
    xs = [x0 + label_w + gap + i * (cw + gap) for i in range(n)]
    els = []
    for x, c in zip(xs, cols):
        els += [R(x, y, cw, head_h, NAVY, r=0.06), T(x + 0.12, y, cw - 0.24, head_h, c, size=15, bold=True, color=LIGHT, valign='m')]
    for j, lab in enumerate(row_labels):
        yy = y + head_h + gap + j * (row_h + 0.06)
        last = highlight_last and j == len(row_labels) - 1
        els += [R(x0, yy, label_w, row_h, ORTINT if last else BLUETINT, r=0.06),
                T(x0 + 0.11, yy, label_w - 0.15, row_h, lab, size=14, font=B, bold=True, color=BURNT if last else BLUE, valign='m')]
        for x, cell in zip(xs, cells[j]):
            els += [R(x, yy, cw, row_h, CREAM, CREAMLINE, lw=0.75, r=0.06), T(x + 0.12, yy, cw - 0.24, row_h, cell, size=size, valign='m')]
    return els


def table(headers, widths, rows, y=1.70, x0=0.89, head_h=0.44, row_h=0.5, size=13, zebra=True, bold_col=None,
          col_colors=None):
    """Simple ruled table drawn with shapes (renders identically in PPTX and HTML)."""
    els = [R(x0, y, sum(widths), head_h, NAVY, r=0)]
    xs = [x0 + sum(widths[:i]) for i in range(len(widths))]
    for x, w, hd in zip(xs, widths, headers):
        els.append(T(x + 0.12, y, w - 0.2, head_h, hd, size=size + 1, font=B, bold=True, color=LIGHT, valign='m'))
    for r_, row in enumerate(rows):
        yy = y + head_h + r_ * row_h
        els.append(R(x0, yy, sum(widths), row_h, CREAM if (zebra and r_ % 2 == 0) else WHITE, CREAMLINE, lw=0.75, r=0))
        for c, (x, w, v) in enumerate(zip(xs, widths, row)):
            col = (col_colors or {}).get(c, NAVY)
            els.append(T(x + 0.12, yy, w - 0.2, row_h, v, size=size, bold=(c == bold_col), color=col, valign='m'))
    return els


def numbered_cards(items, y=1.75, h=3.3, x0=0.89, total_w=11.56, gap=0.24, dark=False):
    """Row of numbered cards: items = [(icon, title, text)] (e.g. checklists, takeaways)."""
    n = len(items); w = (total_w - gap * (n - 1)) / n
    els = []
    for i, (ic, t, q) in enumerate(items):
        x = x0 + i * (w + gap)
        els += [R(x, y, w, h, NAVY if dark else CREAM, None if dark else CREAMLINE, r=0.1), R(x, y, w, 0.07, ORANGE, r=0),
                T(x + 0.18, y + 0.18, 0.8, 0.55, str(i + 1), size=28, bold=True, color=ORANGE)]
        if ic:
            els.append(ICON(ic, x + w - 0.62, y + 0.24, 0.42, PEACH if dark else BLUE))
        els += [T(x + 0.18, y + 0.86, w - 0.36, 0.66, t, size=17, bold=True, color=LIGHT if dark else NAVY),
                T(x + 0.18, y + 1.56, w - 0.36, h - 1.66, q, size=15, color=PALEBLUE if dark else GREY2)]
    return els


def ref(author_year, title, rest, short_url, url):
    """One references-slide entry: Author (year). *Title*. rest short-url(link)."""
    return P([(f'{author_year} ', {}), (title, {'italic': True}), (f'{rest} ', {}),
              (short_url, {'underline': True, 'link': url})], gap=0.1)


def cover(subtitle=None, kicker=None, question=None, presenter=None, affiliation=None):
    """Title-slide elements (a logo, if any, is added by chrome()). ONLY these: optional kicker
    (series/event name the user gave),
    subtitle, opening question (only if the user provided or approved one), presenter name and
    affiliation (only if the user provided them). Nothing else: no illustrations, mock-ups,
    cards or icons on the title slide. The title itself is the slide's `title` field."""
    els = []
    if kicker:
        els.append(T(0.89, 1.38, 7.6, 0.38, kicker.upper(), size=20, font=B, bold=True, color=PEACH, spc=150))
    y = 2.78
    if subtitle:
        h = text_h(subtitle, 9.0, 28, B) + 0.05
        els.append(T(0.89, y, 9.0, h, subtitle, size=28, font=B, color=PALEBLUE))
        y += h + 0.2
    if question:
        qh = text_h(question, 8.4, 20, B, italic=True) + 0.05
        bh = qh + 0.75
        els += [R(0.89, y, 8.9, bh, NAVY2, r=0.1), R(0.89, y, 0.06, bh, ORANGE, r=0),
                T(1.17, y + 0.16, 8.4, 0.38, 'OPENING QUESTION', size=20, font=B, bold=True, color=PEACH, spc=100),
                T(1.17, y + 0.58, 8.4, qh, question, size=20, font=B, italic=True, color=LIGHT)]
        y += bh + 0.2
    if presenter or affiliation:
        paras = []
        if presenter:
            paras.append(P(presenter, size=20, bold=True, color=LIGHT))
        if affiliation:
            paras.append(P(affiliation, size=16, color=PALEBLUE))
        # below the content, above the bottom strip (y > 6.45 is kept free for a bottom logo)
        els.append(T(0.89, max(y + 0.15, 5.35), 9.0, 0.95, paras, size=18, font=B, color=LIGHT, gap=0.04))
    return els
