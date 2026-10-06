#!/usr/bin/env python3
"""Build a deck from a spec module.

  python build.py SPEC.py --template ../assets/blank-template.pptx --out deck.pptx \
      [--preview preview.html] [--slides-dir DIR --blobs blobs.json]

SPEC.py defines SLIDES (list of slide dicts) and optionally THEME, TITLE, SECTIONS
(list of (first_slide_id, one-sentence description)) for the Slides deck index.
"""
import argparse, datetime, importlib.util, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from render_pptx import build as build_pptx
from render_html import section, preview_page


def load(spec_path):
    sys.path.insert(0, os.path.dirname(os.path.abspath(spec_path)))
    sp = importlib.util.spec_from_file_location('deckspec', spec_path)
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    return m


def main():
    a = argparse.ArgumentParser()
    a.add_argument('spec'); a.add_argument('--template', default=os.path.join(HERE, '..', 'assets', 'blank-template.pptx'))
    a.add_argument('--out', default='deck.pptx'); a.add_argument('--preview')
    a.add_argument('--slides-dir'); a.add_argument('--blobs', help='JSON {local image basename: /_blob/... url}')
    o = a.parse_args()
    m = load(o.spec)
    slides, theme = m.SLIDES, getattr(m, 'THEME', None)
    ids = [s['id'] for s in slides]
    assert len(ids) == len(set(ids)), 'slide ids must be unique'
    build_pptx(slides, o.out, o.template, theme)
    print('pptx:', o.out, len(slides), 'slides')
    if o.preview:
        open(o.preview, 'w').write(preview_page(slides, theme)); print('preview:', o.preview)
    if o.slides_dir:
        blobs = json.load(open(o.blobs)) if o.blobs else {}
        def src(p):
            b = os.path.basename(p)
            if b not in blobs:
                raise SystemExit(f'upload {p} as an asset first and add it to --blobs')
            return blobs[b]
        os.makedirs(f'{o.slides_dir}/project/slides', exist_ok=True)
        for i, sd in enumerate(slides, 1):
            notes = sd.get('notes', '')
            if len(notes) > 4000:
                raise SystemExit(f'{sd["id"]}: notes {len(notes)} chars > 4000 (Slides limit)')
            open(f'{o.slides_dir}/project/slides/{sd["id"]}.html', 'w').write(section(sd, i, src, theme) + '\n')
        fonts = sorted({'Montserrat', 'IBM Plex Sans', 'IBM Plex Mono', 'Source Serif 4'} if not theme or 'fonts' not in theme else theme['fonts'])
        secs = getattr(m, 'SECTIONS', [(ids[0], 'Deck')])
        deck = {"v": 4, "createdOnFiles": {"v": 1, "at": datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}, "lists": "css",
                "title": getattr(m, 'TITLE', slides[0]['title']), "order": ids, "cover": ids[0],
                "sections": {f's{i+1}': {"description": d, "start": sid} for i, (sid, d) in enumerate(secs)},
                "faces": {f.lower().replace(' ', '-'): {"family": f, "href": "https://fonts.googleapis.com/css2?family=" + f.replace(' ', '+') + ":ital,wght@0,400;0,700;1,400;1,700&display=swap"} for f in fonts[:4]},
                "designSystems": []}
        json.dump(deck, open(f'{o.slides_dir}/project/deck.json', 'w'), indent=1, ensure_ascii=False)
        print('slides deck files:', o.slides_dir)


if __name__ == '__main__':
    main()
