#!/usr/bin/env python3
"""Collect the user's own material after the upload step (references/intake-questions.md).

  python collect_sources.py --links "https://a.org/x, https://b.org/y
  https://c.org/z" --files report.pdf data.xlsx chart.png --out sources.json

- Links: split on commas, new lines, semicolons or spaces; trailing punctuation removed;
  only http/https kept; duplicates removed (order kept). Bare domains like example.org/page
  get https:// added.
- Files: listed with their type and how to read them; missing files are reported.
Writes sources.json: {"links": [...], "files": [{path, type, read_with}], "problems": [...]}.
Prints a short summary for the reply to the user.
"""
import argparse, json, os, re

READ = {
    'pdf': 'pdf-reading skill (text + page images for figures/tables)',
    'docx': 'docx skill / python-docx (text, tables)',
    'doc': 'convert with soffice --convert-to docx, then as docx',
    'pptx': 'python-pptx (slide text, notes, images)',
    'xlsx': 'pandas.read_excel (every sheet); compute figures in code',
    'xls': 'pandas.read_excel (every sheet); compute figures in code',
    'csv': 'pandas.read_csv; compute figures in code',
    'tsv': 'pandas.read_csv(sep="\\t"); compute figures in code',
    'txt': 'read as text', 'md': 'read as text', 'json': 'json.load', 'html': 'read text (strip tags)',
    'htm': 'read text (strip tags)',
    'png': 'view the image (Read tool); describe charts, do not invent values',
    'jpg': 'view the image (Read tool)', 'jpeg': 'view the image (Read tool)', 'webp': 'view the image (Read tool)',
}


def split_links(text):
    out, seen = [], set()
    for tok in re.split(r'[\s,;]+', text or ''):
        tok = tok.strip().strip('<>()[]"\'').rstrip('.,;:!?')
        if not tok:
            continue
        if not re.match(r'https?://', tok, re.I):
            if re.match(r'^[\w-]+(\.[\w-]+)+(/\S*)?$', tok):
                tok = 'https://' + tok
            else:
                continue
        if tok.lower() not in seen:
            seen.add(tok.lower()); out.append(tok)
    return out


def main():
    a = argparse.ArgumentParser()
    a.add_argument('--links', default=''); a.add_argument('--files', nargs='*', default=[])
    a.add_argument('--out', default='sources.json')
    o = a.parse_args()
    links = split_links(o.links)
    files, problems = [], []
    for f in o.files:
        ext = os.path.splitext(f)[1].lower().lstrip('.')
        if not os.path.exists(f):
            problems.append(f'file not found: {f}')
            continue
        files.append(dict(path=f, type=ext or 'unknown', read_with=READ.get(ext, 'unsupported type: ask the user for PDF, Office, CSV, text or image')))
        if ext not in READ:
            problems.append(f'unsupported type: {f}')
    json.dump(dict(links=links, files=files, problems=problems), open(o.out, 'w'), indent=1)
    print(f'{len(files)} file(s), {len(links)} link(s) -> {o.out}')
    for x in links:
        print('  link:', x)
    for f in files:
        print(f'  file: {f["path"]} [{f["type"]}] -> {f["read_with"]}')
    for p in problems:
        print('  PROBLEM:', p)


if __name__ == '__main__':
    main()
