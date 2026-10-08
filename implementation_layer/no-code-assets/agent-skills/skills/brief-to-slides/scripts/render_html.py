"""Render the same deck spec as Slides-deck sections (1920x1080 canvas, 1 in = 144 px)
and as a local preview page used by check_deck.py. See references/slides-artifact.md."""
import html
import os
import re
from dsl import *
from render_pptx import icon_svg

PX = 144
JUST = {'t': 'start', 'm': 'center', 'b': 'end'}
TA = {'l': 'left', 'c': 'center', 'r': 'right'}
FALLBACK = {S: "Georgia, serif", M: "'Courier New', monospace"}


def px(v):
    return int(round(v * PX))


def stack(font):
    return f"'{font}', {FALLBACK.get(font, 'Arial, sans-serif')}"


def esc(s):
    return html.escape(s, quote=False)


def runs_html(runs, base):
    out = []
    for text, st in runs:
        s = esc(text)
        if st.get('color') and st['color'] != base['color']:
            s = f'<span style="color:#{st["color"]}">{s}</span>'
        if st.get('italic') and not base['italic']:
            s = f'<i>{s}</i>'
        if st.get('bold') and not base['bold']:
            s = f'<b>{s}</b>'
        if st.get('link'):
            s = f'<a href="{html.escape(st["link"])}"><span style="color:#{base["color"]}">{s}</span></a>'
        elif st.get('underline'):
            s = f'<u>{s}</u>'
        out.append(s)
    return ''.join(out)


def text_html(el, tag='p'):
    parts = []
    for i, p in enumerate(el['paras']):
        size = p.get('size', el['size']); font = p.get('font', el['font'])
        bold = p.get('bold', el['bold']); italic = p.get('italic', el['italic'])
        color = p.get('color', el['color']); align = p.get('align', el['align'])
        lh = p.get('lh', el['lh']); spc = p.get('spc', el['spc'])
        st = [f'font-family:{stack(font)}', f'font-size:{round(size * 2)}px', f'line-height:{lh * line_factor(font):.3f}',
              f'color:#{color}', f'font-weight:{700 if bold else 400}', f'text-align:{TA[align]}']
        if italic:
            st.append('font-style:italic')
        if spc:
            st.append(f'letter-spacing:{spc / 50:.1f}px')
        runs = p['runs']
        if font == M:  # keep spacing in code/file trees (no white-space:pre in the Slides subset)
            runs = [(t.replace(' ', ' '), s_) for t, s_ in runs]
        tg = tag if i == 0 else 'p'
        parts.append(f'<{tg} style="{";".join(st)}">{runs_html(runs, dict(color=color, bold=bold, italic=italic))}</{tg}>')
    style = (f"position:absolute;left:{px(el['x'])}px;top:{px(el['y'])}px;width:{px(el['w'])}px;height:{px(el['h'])}px;"
             f"display:flex;flex-direction:column;justify-content:{JUST[el['valign']]};gap:{px(el['gap'])}px")
    return f'<div style="{style}">' + ''.join(parts) + '</div>'


def el_html(el, img_src):
    t = el['t']
    if t in ('rect', 'ellipse'):
        st = f"position:absolute;left:{px(el['x'])}px;top:{px(el['y'])}px;width:{px(el['w'])}px;height:{px(el['h'])}px"
        if el['fill']:
            st += f";background:#{el['fill']}"
        if el['line']:
            st += f";border:{max(1, round(el['lw'] * 2))}px {'dashed' if el.get('dash') else 'solid'} #{el['line']}"
        if t == 'ellipse':
            st += ';border-radius:50%'
        elif el['r']:
            st += f";border-radius:{px(min(el['r'], min(el['w'], el['h']) / 2))}px"
        return f'<div style="{st}"></div>'
    if t == 'text':
        return text_html(el)
    if t == 'line':
        if el['head'] is None and not el['dash'] and (el['x1'] == el['x2'] or el['y1'] == el['y2']):
            w = max(px(abs(el['x2'] - el['x1'])), round(el['lw'] * 2)); h = max(px(abs(el['y2'] - el['y1'])), round(el['lw'] * 2))
            return (f'<div style="position:absolute;left:{px(min(el["x1"], el["x2"]))}px;top:{px(min(el["y1"], el["y2"]))}px;'
                    f'width:{w}px;height:{h}px;background:#{el["color"]}"></div>')
        st = f"color:#{el['color']};border-width:{max(1, round(el['lw'] * 2))}px" + (';border-style:dashed' if el['dash'] else '')
        return (f'<x-connector x1="{px(el["x1"])}" y1="{px(el["y1"])}" x2="{px(el["x2"])}" y2="{px(el["y2"])}" '
                f'head="{el["head"] or "none"}" route="straight" style="{st}"></x-connector>')
    if t == 'arrow':
        kind = {'r': 'arrow-right', 'l': 'arrow-left', 'd': 'arrow-down', 'u': 'arrow-up'}[el['d']]
        return (f'<x-shape kind="{kind}" style="position:absolute;left:{px(el["x"])}px;top:{px(el["y"])}px;'
                f'width:{px(el["w"])}px;height:{px(el["h"])}px;background:#{el["color"]}"></x-shape>')
    if t == 'img':
        return (f'<img src="{img_src(el["path"])}" alt="{html.escape(el.get("alt", ""))}" style="position:absolute;'
                f'left:{px(el["x"])}px;top:{px(el["y"])}px;width:{px(el["w"])}px;height:{px(el["h"])}px;object-fit:contain">')
    if t == 'icon':
        s = icon_svg(el['name'], el['color'], el['sw']); S_ = px(el['s']); k = S_ / 24
        inner = re.sub(r'\s+', ' ', s[s.index('>') + 1: s.rindex('</svg>')]).strip()
        return (f'<svg aria-label="" xmlns="http://www.w3.org/2000/svg" width="{S_}" height="{S_}" viewBox="0 0 {S_} {S_}" '
                f'style="position:absolute;left:{px(el["x"])}px;top:{px(el["y"])}px;width:{S_}px;height:{S_}px">'
                f'<g transform="scale({k:.4f})" fill="none" stroke="#{el["color"]}" stroke-width="{el["sw"]}" '
                f'stroke-linecap="round" stroke-linejoin="round">{inner}</g></svg>')
    raise ValueError(t)


def section(sd, n, img_src, theme=None):
    th = resolve_theme(theme)
    cover = sd['kind'] == 'title'
    bg = th['title_bg'] if cover else (th['content_bg'] or 'FFFFFF')
    if bg == 'accent1':
        bg = BRAND
    out = [f'<section id="{sd["id"]}" data-transition="fade" style="background:#{bg};color:#{NAVY};'
           f'font-family:{stack(H)};padding:128px 128px 160px;display:flex;flex-direction:column">']
    if not cover and th['footer_band']:
        x, y, w, h = th['footer_band']['box']
        out.append(f'<div style="position:absolute;left:{px(x)}px;top:{px(y)}px;width:{px(w)}px;height:{1080 - px(y)}px;'
                   f'background:#{th["footer_band"]["color"]}"></div>')
    if cover:
        c = th['cover_title']
        out.append(text_html(T(*c['box'], sd['title'], size=c['size'], font=c['font'], bold=True, color=c['color'], valign='b'), 'h1'))
    else:
        c = th['title']
        out.append(text_html(T(*title_box(sd, th), sd['title'], size=c['size'], font=c['font'], bold=True, color=c['color']), 'h2'))
    for el in sd['els']:
        out.append(el_html(el, img_src))
    for el in chrome(sd, n, th):
        out.append(el_html(el, img_src))
    notes = sd.get('notes', '')
    out.append(f'<aside>{esc(notes)}</aside>')
    out.append('</section>')
    return '\n'.join(out)


POLYFILL = """<script>
document.querySelectorAll('section').forEach(sec=>{
 sec.querySelectorAll('x-connector').forEach(c=>{
  const [x1,y1,x2,y2]=['x1','y1','x2','y2'].map(a=>+c.getAttribute(a)); const col=c.style.color; const w=parseFloat(c.style.borderWidth)||2;
  const dash=c.style.borderStyle==='dashed'?'stroke-dasharray="8 6"':''; const head=c.getAttribute('head'); const id='m'+Math.random().toString(36).slice(2);
  c.outerHTML=`<svg style="position:absolute;left:0;top:0;width:1920px;height:1080px" viewBox="0 0 1920 1080"><defs><marker id="${id}" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto-start-reverse" markerUnits="strokeWidth"><path d="M0,0 L6,3 L0,6 z" fill="${col}"/></marker></defs><line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${col}" stroke-width="${w}" ${dash} ${head==='end'||head==='both'?`marker-end="url(#${id})"`:''} ${head==='both'?`marker-start="url(#${id})"`:''}/></svg>`;});
 sec.querySelectorAll('x-shape').forEach(s=>{
  const k=s.getAttribute('kind'), w=parseFloat(s.style.width), h=parseFloat(s.style.height), col=s.style.background||s.style.backgroundColor; let p;
  if(k==='arrow-right') p=`0,${h*.25} ${w*.6},${h*.25} ${w*.6},0 ${w},${h/2} ${w*.6},${h} ${w*.6},${h*.75} 0,${h*.75}`;
  else if(k==='arrow-left') p=`${w},${h*.25} ${w*.4},${h*.25} ${w*.4},0 0,${h/2} ${w*.4},${h} ${w*.4},${h*.75} ${w},${h*.75}`;
  else if(k==='arrow-down') p=`${w*.25},0 ${w*.75},0 ${w*.75},${h*.6} ${w},${h*.6} ${w/2},${h} 0,${h*.6} ${w*.25},${h*.6}`;
  else p=`${w*.25},${h} ${w*.75},${h} ${w*.75},${h*.4} ${w},${h*.4} ${w/2},0 0,${h*.4} ${w*.25},${h*.4}`;
  s.outerHTML=`<svg style="position:absolute;left:${s.style.left};top:${s.style.top};width:${w}px;height:${h}px"><polygon points="${p}" fill="${col}"/></svg>`;});
});
</script>"""


def preview_page(slides, theme=None):
    secs = [section(sd, i, lambda p: 'file://' + os.path.abspath(p), theme) for i, sd in enumerate(slides, 1)]
    return ('<!doctype html><html><head><meta charset="utf-8"><style>section{position:relative;width:1920px;height:1080px;'
            'overflow:hidden;box-sizing:border-box;margin:0 0 20px 0} section p,section h1,section h2{margin:0} aside{display:none}'
            '</style></head><body style="margin:0;background:#999">' + '\n'.join(secs) + POLYFILL + '</body></html>')

