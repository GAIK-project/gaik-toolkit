"""Turn a source tracing report into one self-contained HTML page.

``write_trace_view`` takes what ``SourceTracing.check_pdf`` returned and writes a single
HTML file, with no server and no external files: the PDF pages are embedded as images, and the
quote of every value is drawn over its page from the boxes in ``TracedValue.rects``. The page
explains each part of the report, so a reader who has never seen source tracing can follow it.

It is also a worked example of using the boxes in your own interface: the function that
draws them (``DRAW_BOXES_JS``) is shown on the page and is the code the page itself runs.
Nothing here is part of the gaik package; copy what you need.
"""

# The page template is HTML, CSS and JavaScript: its long lines are intentional.
# ruff: noqa: E501

from __future__ import annotations

import base64
import html
import json
from pathlib import Path

import pymupdf

COLOURS = {
    "verified": "#16a34a",
    "check": "#dc2626",
    "reworded": "#f97316",
    "unchecked": "#6b7280",
}

# The code that draws the boxes of one value over its page. The page runs it, and shows it.
DRAW_BOXES_JS = """\
// container: an element with position: relative that has the same aspect ratio as the
// page image. A box is {x, y, w, h}: fractions of the page, from 0 to 1, measured from the
// top left corner, so percentages place it correctly at any size. In the CSS, a box uses
// box-sizing: content-box and a negative margin, so its border is drawn outside the word.
function drawBoxes(container, item, colour) {
  const made = [];
  for (const r of item.rects) {                  // the words of the quote: an outline
    const box = document.createElement("div");
    box.className = "box";
    Object.assign(box.style, {
      left: r.x * 100 + "%", top: r.y * 100 + "%",
      width: r.w * 100 + "%", height: r.h * 100 + "%",
      borderColor: colour,                       // the colour of the verdict
    });
    container.appendChild(box);
    made.push(box);
  }
  for (const r of item.value_rects) {            // the value inside the quote: a fill
    const box = document.createElement("div");
    box.className = "box value";
    Object.assign(box.style, {
      left: r.x * 100 + "%", top: r.y * 100 + "%",
      width: r.w * 100 + "%", height: r.h * 100 + "%",
      borderColor: colour,
    });
    container.appendChild(box);
    made.push(box);
  }
  return made;
}
"""

STATUS_TEXT = {
    "found": "The quote is on the page the model named.",
    "moved": "The quote is in the document, but on another page or file than the model named.",
    "not_found": "The quote is not in the document.",
    "no_text_layer": "The file has no text layer to look in (a scan or an image).",
}


def explain(item: dict) -> str:
    """One sentence on why an item got its verdict, for a reader who sees it for the first time."""
    value, verdict, status = item["value"], item["verdict"], item["status"]
    where = f"page {item['page']}"
    if verdict == "verified":
        return (
            f"The quote was found on {where} and the value is in it, so the model's answer "
            "agrees with the text it cited."
        )
    if status == "no_text_layer":
        return (
            "This file has no text layer (it is a scan or an image), so the quote can not be "
            "looked up. A person has to read the page."
        )
    if status == "not_found":
        return (
            "The quote was not found anywhere in the document, so there is nothing to check "
            "the value against. The model probably paraphrased the text instead of copying "
            "it. Read the page to see whether the value is right."
        )
    if verdict == "reworded":
        return (
            f"The quote was found on {where}, but the text value is not in it. That usually "
            "means the model wrote the value in its own words, for example a translation or "
            "a summary. The evidence is real; the wording is the model's."
        )
    if verdict == "check":
        return (
            f"The quote was found on {where}, but it holds a different number or date than the "
            "value. The value may be a legitimate conversion, such as another unit, or it "
            "may be a mistake. Compare the highlighted text with the value."
        )
    if isinstance(value, list):
        return (
            "The value is a list, and one quote can not show a whole list. A person has to "
            "check the items against the page."
        )
    return "The value can not be compared with the quote, so a person has to check it."


def _page_images(pdf_paths: list[Path], dpi: int = 110) -> list[dict]:
    pages = []
    for number, path in enumerate(pdf_paths, start=1):
        with pymupdf.open(path) as doc:
            for index, page in enumerate(doc, start=1):
                pixmap = page.get_pixmap(dpi=dpi)
                data = base64.b64encode(pixmap.tobytes("jpeg", jpg_quality=82)).decode()
                pages.append(
                    {
                        "document": number,
                        "page": index,
                        "name": path.name,
                        "width": pixmap.width,
                        "height": pixmap.height,
                        "image": f"data:image/jpeg;base64,{data}",
                    }
                )
    return pages


def _json_for_script(value) -> str:
    # Safe inside <script type="application/json">: no "</" can end the element early.
    return json.dumps(value, ensure_ascii=False, default=str).replace("</", "<\\/")


def write_trace_view(
    out_path: str | Path,
    *,
    pdf_paths: list[str | Path],
    report,
    clean_results,
    task_prompt: str,
    task_text: str,
    notes: list[str] | None = None,
) -> Path:
    """Write the self-contained HTML page and return its path.

    Args:
        out_path: Where to write the page.
        pdf_paths: The PDFs that were checked, in the order given to ``check_pdf``.
        report: The ``TraceReport`` from ``SourceTracing.check_pdf``.
        clean_results: The results ``check_pdf`` returned (without the evidence).
        task_prompt: The task text sent to the extractor (``Augmented.prompt``).
        task_text: The task text before ``augment`` added the evidence request.
        notes: Optional extra sentences to show under "About this run".
    """
    paths = [Path(p) for p in pdf_paths]
    payload = report.to_dict()
    for item in payload["sources"]:
        item["why"] = explain(item)
        item["status_text"] = STATUS_TEXT[item["status"]]
    data = {
        "report": payload,
        "pages": _page_images(paths),
        "colours": COLOURS,
    }
    instruction = task_prompt[len(task_text) :].strip() if task_prompt.startswith(task_text) else ""
    page = (
        _TEMPLATE.replace("__TITLE__", html.escape(", ".join(p.name for p in paths)))
        .replace("__DATA__", _json_for_script(data))
        .replace("__TASK__", html.escape(task_text.strip()))
        .replace("__INSTRUCTION__", html.escape(instruction))
        .replace(
            "__RESULTS__",
            html.escape(json.dumps(clean_results, indent=2, ensure_ascii=False, default=str)),
        )
        .replace(
            "__SAMPLE__",
            html.escape(
                json.dumps(
                    {**payload["sources"][0]} if payload["sources"] else {},
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                )
            ),
        )
        .replace("__DRAW_JS__", html.escape(DRAW_BOXES_JS))
        .replace("__DRAW_JS_RAW__", DRAW_BOXES_JS.replace("</", "<\\/"))
        .replace("__NOTES__", "".join(f"<li>{html.escape(n)}</li>" for n in (notes or [])))
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<title>Source tracing: __TITLE__</title>
<style>
  :root { --verified:#16a34a; --check:#dc2626; --reworded:#f97316; --unchecked:#6b7280;
          --ink:#1f2937; --muted:#6b7280; --line:#e5e7eb; --bg:#f8fafc; --blue:#1d4ed8; }
  * { box-sizing: border-box; }
  body { margin:0; font:15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; color:var(--ink); background:var(--bg); }
  header { background:#fff; border-bottom:1px solid var(--line); padding:20px 28px; }
  header h1 { margin:0 0 4px; font-size:22px; }
  header p { margin:0; color:var(--muted); max-width:900px; }
  main { max-width:1500px; margin:0 auto; padding:20px 28px 60px; }
  section.card { background:#fff; border:1px solid var(--line); border-radius:10px; padding:16px 20px; margin-bottom:16px; }
  section.card h2 { margin:0 0 8px; font-size:17px; }
  ol.steps { margin:6px 0 0; padding-left:22px; } ol.steps li { margin:6px 0; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:10px; margin-top:10px; }
  .vcard { border:1px solid var(--line); border-left:6px solid var(--c); border-radius:8px; padding:8px 12px; background:#fff; }
  .vcard b { font-size:22px; display:block; line-height:1.1; }
  .vcard span { color:var(--muted); font-size:13px; }
  .swatch { display:inline-block; width:14px; height:14px; border:3px solid var(--c); border-radius:3px; vertical-align:-2px; margin-right:6px; }
  .swatch.fill { background:rgba(29,78,216,.25); border-color:var(--blue); }
  table.legend { border-collapse:collapse; width:100%; margin-top:6px; }
  table.legend td { padding:6px 8px; border-top:1px solid var(--line); vertical-align:top; }
  details { margin:8px 0; } summary { cursor:pointer; font-weight:600; }
  pre { background:#0f172a; color:#e2e8f0; border-radius:8px; padding:12px 14px; overflow:auto; font:12.5px/1.45 ui-monospace, Consolas, monospace; max-height:420px; }
  pre.light { background:#f1f5f9; color:#0f172a; }
  .layout { display:grid; grid-template-columns:minmax(360px,440px) 1fr; gap:18px; align-items:start; }
  @media (max-width: 1000px) { .layout { grid-template-columns:1fr; } }
  .side { position:sticky; top:12px; max-height:calc(100vh - 24px); display:flex; flex-direction:column; gap:10px; }
  .panel { background:#fff; border:1px solid var(--line); border-radius:10px; padding:12px; }
  .filters { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:8px; }
  .chip { border:1px solid var(--line); background:#fff; border-radius:999px; padding:3px 10px; font-size:13px; cursor:pointer; }
  .chip.on { background:var(--ink); color:#fff; border-color:var(--ink); }
  .toggles { font-size:13px; color:var(--muted); display:flex; gap:14px; flex-wrap:wrap; margin-top:6px; }
  #list { overflow:auto; max-height:34vh; margin:0; padding:0; list-style:none; }
  #list li { display:grid; grid-template-columns:auto 1fr; gap:2px 8px; padding:6px 8px; border-radius:6px; cursor:pointer; border-left:5px solid var(--c); margin:2px 0; }
  #list li:hover { background:#f1f5f9; } #list li.sel { background:#e0e7ff; }
  #list .f { font-weight:600; word-break:break-all; } #list .v { color:var(--muted); grid-column:2; word-break:break-word; font-size:13px; }
  .badge { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.03em; color:#fff; background:var(--c); border-radius:4px; padding:1px 6px; align-self:start; }
  #detail { overflow:auto; font-size:14px; }
  #detail h3 { margin:0 0 6px; font-size:15px; } #detail .why { background:#fffbeb; border:1px solid #fde68a; border-radius:8px; padding:8px 10px; margin:8px 0; }
  #detail dl { display:grid; grid-template-columns:auto 1fr; gap:3px 10px; margin:8px 0 0; }
  #detail dt { color:var(--muted); } #detail dd { margin:0; word-break:break-word; }
  #detail .quote { background:#f1f5f9; border-left:3px solid var(--c); padding:6px 8px; border-radius:4px; font-family:ui-monospace, Consolas, monospace; font-size:13px; white-space:pre-wrap; }
  .pages { display:flex; flex-direction:column; gap:22px; }
  .pagewrap h4 { margin:0 0 6px; font-size:14px; color:var(--muted); }
  .page { position:relative; max-width:820px; border:1px solid var(--line); box-shadow:0 1px 4px rgba(0,0,0,.08); background:#fff; }
  .page img { display:block; width:100%; height:auto; }
  /* A box is the rectangle of a word, from the PDF. Its border is drawn just OUTSIDE that rectangle
     (content-box and a negative margin), so the border never covers the letters it points at. */
  .box { position:absolute; border:2px solid; box-sizing:content-box; margin:-2px 0 0 -2px; cursor:pointer; opacity:.85; transition:opacity .15s; }
  /* The value inside the quote is a light fill that multiplies with the page, so the text stays readable. */
  .box.value { background:rgba(29,78,216,.16); mix-blend-mode:multiply; }
  /* Once a value is selected, every other box fades into the background... */
  .has-selection .box:not(.selected) { opacity:.14; border-width:1px; margin:-1px 0 0 -1px; }
  /* ...and the selected one gets a thicker border and a halo that pulses, all outside the words. */
  .box.selected { opacity:1; border-width:3px; margin:-3px 0 0 -3px; z-index:5; box-shadow:0 0 0 2px #fff, 0 0 0 4px rgba(0,0,0,.5); animation:pulse 1.1s ease-out 3; }
  .box.value.selected { background:rgba(29,78,216,.2); }
  @keyframes pulse { 0% { box-shadow:0 0 0 2px #fff, 0 0 0 4px rgba(0,0,0,.5), 0 0 0 4px rgba(250,204,21,.9); }
                     100% { box-shadow:0 0 0 2px #fff, 0 0 0 4px rgba(0,0,0,.5), 0 0 0 24px rgba(250,204,21,0); } }
  /* A label above the selected quote says which value it is. */
  .tag { position:absolute; z-index:6; background:var(--c); color:#fff; font-size:12px; font-weight:700; padding:2px 8px; border-radius:4px; white-space:nowrap; pointer-events:none; box-shadow:0 1px 4px rgba(0,0,0,.4); }
  .only-selected .box:not(.selected) { display:none; }
  .hide-value .box.value { background:transparent; }
  #tip { position:fixed; z-index:50; pointer-events:none; background:#111827; color:#fff; padding:6px 9px; border-radius:6px; font-size:12.5px; max-width:340px; display:none; }
  code { background:#f1f5f9; padding:0 4px; border-radius:4px; font-size:13px; }
  footer { color:var(--muted); font-size:13px; margin-top:20px; }
</style>
</head>
<body>
<header>
  <h1>Source tracing report <span style="color:var(--muted);font-weight:400">&middot; __TITLE__</span></h1>
  <p>Every value the extractor returned comes with a short quote from the document. This page shows where each quote
  sits on the page, and whether the value really is in it. Click a value on the left: its quote is drawn thick and labelled on the page, and the quotes of all the other values fade into the background.</p>
</header>
<main>

<section class="card" id="how">
  <h2>What you are looking at</h2>
  <ol class="steps">
    <li><b>The extractor was asked for evidence.</b> <code>SourceTracing.augment</code> added a request to the task:
        for every value, give the document, the page and a short quote copied exactly from the document. The extraction
        schema is unchanged apart from one extra field that holds these citations.</li>
    <li><b>The extractor ran as usual</b> and returned the values together with their quotes. No part of source
        tracing is a model: it only checks what the extractor returned.</li>
    <li><b>Plain code checked each citation.</b> It looked for the quote in the PDF's own text (ignoring case,
        punctuation and spacing), compared the value with the quote (numbers as numbers, dates as dates), and
        took the position of the quoted words from the PDF, so the model never has to give coordinates.</li>
    <li><b>The result is this page.</b> Each value has a verdict, and a quote you can see on its page.</li>
  </ol>
  <details><summary>The task that was given to the extractor</summary>
    <p style="margin:6px 0 2px">The task text:</p><pre class="light">__TASK__</pre>
    <p style="margin:6px 0 2px">The evidence request that <code>augment</code> appended to it:</p><pre class="light">__INSTRUCTION__</pre>
  </details>
  <ul id="notes" style="margin:6px 0 0;padding-left:20px">__NOTES__</ul>
</section>

<section class="card" id="summary">
  <h2>The result in numbers</h2>
  <div class="cards" id="cards"></div>
  <p id="coverage" style="margin:10px 0 0;color:var(--muted)"></p>
</section>

<section class="card" id="legend">
  <h2>How to read the verdicts and the colours</h2>
  <table class="legend">
    <tr><td style="width:160px"><span class="swatch" style="--c:var(--verified)"></span><b>verified</b></td>
        <td>The quote is in the document and the value is in the quote. Nothing to do, or a quick glance.</td></tr>
    <tr><td><span class="swatch" style="--c:var(--check)"></span><b>check</b></td>
        <td>The quote is not in the document, or it holds a different number or date than the value. Look at it: the value may be wrong, or a legitimate conversion.</td></tr>
    <tr><td><span class="swatch" style="--c:var(--reworded)"></span><b>reworded</b></td>
        <td>The quote is in the document but a text value is not in it. Usually the model's own wording, such as a translation or a summary.</td></tr>
    <tr><td><span class="swatch" style="--c:var(--unchecked)"></span><b>unchecked</b></td>
        <td>Cannot be compared: a list, a number written in words, or a scan without a text layer. A person checks it.</td></tr>
    <tr><td><span class="swatch fill"></span><b>blue fill</b></td>
        <td>Not a verdict: it marks the exact words of the value inside its quote. It is drawn only when the value can be located there.</td></tr>
  </table>
  <p style="margin:8px 0 0;color:var(--muted)">A box is drawn around every <b>word</b> of the quote, in the colour of the verdict. A verified value matches its quote. That is not proof that the quote is the right place to read it.</p>
</section>

<section class="layout" id="viewer">
  <div class="side">
    <div class="panel">
      <div class="filters" id="filters"></div>
      <ul id="list"></ul>
      <div class="toggles">
        <label><input type="checkbox" id="onlySel"> hide the other values' boxes (they are faded by default)</label>
        <label><input type="checkbox" id="noFill"> hide the blue value fill</label>
      </div>
    </div>
    <div class="panel" id="detail"><em>Click a value in the list, or a box on a page, to see why it got its verdict.</em></div>
  </div>
  <div class="pages" id="pages"></div>
</section>

<section class="card" style="margin-top:16px">
  <h2>What your application receives</h2>
  <p style="margin:0 0 6px">Source tracing returns two things: the <b>results without the evidence</b>, in the same
  shape you passed in, and the <b>report</b> that this page draws.</p>
  <details open><summary>The results (<code>clean</code>)</summary><pre>__RESULTS__</pre></details>
  <details><summary>One item of the report (<code>report.to_dict()["sources"][0]</code>)</summary>
    <pre>__SAMPLE__</pre>
    <p style="margin:6px 0 0;color:var(--muted)"><code>rects</code> and <code>value_rects</code> are lists of boxes, as fractions of the page.
    <code>status</code> says where the quote was found, <code>value_status</code> whether the value is in it, and <code>verdict</code> is the result to show a reviewer.</p>
  </details>
</section>

<section class="card">
  <h2>How this page draws the boxes (the code for your own interface)</h2>
  <p style="margin:0 0 6px">This is the function the page runs, unchanged. Show the page image at any size inside a container with
  <code>position: relative</code>, and call it with the item and a colour.</p>
  <pre>__DRAW_JS__</pre>
</section>

<footer>Generated by the source tracing example. A box can only be drawn for a PDF with a text layer; for plain text the report has character offsets instead (<code>span</code>).</footer>
</main>
<div id="tip"></div>

<script type="application/json" id="data">__DATA__</script>
<script>
__DRAW_JS_RAW__
const DATA = JSON.parse(document.getElementById("data").textContent);
const ITEMS = DATA.report.sources;
const COLOURS = DATA.colours;
const boxesOf = new Map();       // item index -> its box elements
let selected = null, filter = "all";

function el(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "text") e.textContent = v;
    else if (k === "style") for (const [name, val] of Object.entries(v)) {
      if (name.startsWith("--")) e.style.setProperty(name, val); else e.style[name] = val;
    }
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  kids.flat().forEach(c => c != null && e.append(c));
  return e;
}
const show = v => typeof v === "string" ? v : JSON.stringify(v);

// ---- summary cards
const S = DATA.report.summary;
const cardsEl = document.getElementById("cards");
for (const v of ["verified", "check", "reworded", "unchecked"]) {
  cardsEl.append(el("div", {class: "vcard", style: {"--c": COLOURS[v]}}, el("b", {text: S[v]}), el("span", {text: v})));
}
cardsEl.append(el("div", {class: "vcard", style: {"--c": "#334155"}}, el("b", {text: S.total}), el("span", {text: "values with a quote"})));
document.getElementById("coverage").textContent =
  S.coverage == null ? "No values were extracted." :
  `Evidence came with ${Math.round(S.coverage * 100)}% of the extracted values (the coverage). A value without a quote cannot be traced.`;

// ---- pages with their boxes
const pagesEl = document.getElementById("pages");
const containers = {};
for (const p of DATA.pages) {
  const box = el("div", {class: "page", id: `page-${p.document}-${p.page}`, style: {aspectRatio: `${p.width} / ${p.height}`}},
                 el("img", {src: p.image, alt: `${p.name} page ${p.page}`}));
  containers[`${p.document}:${p.page}`] = box;
  pagesEl.append(el("div", {class: "pagewrap"}, el("h4", {text: `${p.name} - page ${p.page}`}), box));
}
ITEMS.forEach((item, i) => {
  const c = containers[`${item.document}:${item.page}`];
  if (!c || !item.rects.length) return;
  const made = drawBoxes(c, item, COLOURS[item.verdict]);
  made.forEach(b => {
    b.addEventListener("click", () => select(i, false));
    b.addEventListener("mousemove", ev => tip(ev, item));
    b.addEventListener("mouseleave", () => tipEl.style.display = "none");
  });
  boxesOf.set(i, made);
});

// ---- tooltip
const tipEl = document.getElementById("tip");
function tip(ev, item) {
  tipEl.replaceChildren(el("b", {text: item.field}), el("br"), document.createTextNode(`${show(item.value)}  -  ${item.verdict}`));
  tipEl.style.display = "block";
  tipEl.style.left = Math.min(ev.clientX + 14, innerWidth - 360) + "px";
  tipEl.style.top = ev.clientY + 14 + "px";
}

// ---- list and filters
const listEl = document.getElementById("list");
const filtersEl = document.getElementById("filters");
function renderFilters() {
  filtersEl.replaceChildren();
  for (const f of ["all", "verified", "check", "reworded", "unchecked"]) {
    const n = f === "all" ? ITEMS.length : S[f];
    if (f !== "all" && !n) continue;
    filtersEl.append(el("button", {class: "chip" + (filter === f ? " on" : ""), text: `${f} (${n})`,
                                   onclick: () => { filter = f; renderFilters(); renderList(); }}));
  }
}
function renderList() {
  listEl.replaceChildren();
  ITEMS.forEach((item, i) => {
    if (filter !== "all" && item.verdict !== filter) return;
    const row = el("li", {class: i === selected ? "sel" : "", "data-i": i, style: {"--c": COLOURS[item.verdict]},
                          onclick: () => select(i, true)},
                   el("span", {class: "badge", text: item.verdict}),
                   el("span", {class: "f", text: item.field + (item.record != null ? `  (row ${item.record + 1})` : "")}),
                   el("span", {class: "v", text: `${show(item.value)}  -  page ${item.page}`}));
    listEl.append(row);
  });
}

// ---- detail panel
function detail(item) {
  const d = document.getElementById("detail");
  d.style.setProperty("--c", COLOURS[item.verdict]);
  const moved = item.page !== item.cited_page ? ` (the model said page ${item.cited_page})` : "";
  d.replaceChildren(
    el("h3", {text: item.field}),
    el("span", {class: "badge", text: item.verdict, style: {"--c": COLOURS[item.verdict]}}),
    el("div", {class: "why", text: item.why}),
    el("div", {text: "The quote the model gave:"}),
    el("div", {class: "quote", text: item.quote}),
    el("dl", {},
      el("dt", {text: "value"}), el("dd", {text: show(item.value)}),
      el("dt", {text: "found on"}), el("dd", {text: `document ${item.document}, page ${item.page}${moved}`}),
      el("dt", {text: "status"}), el("dd", {text: `${item.status} - ${item.status_text}`}),
      el("dt", {text: "value in quote"}), el("dd", {text: item.value_status}),
      el("dt", {text: "occurrences"}), el("dd", {text: `${item.occurrences} (how often the quote occurs on that page)`}),
      el("dt", {text: "boxes"}), el("dd", {text: `${item.rects.length} for the quote, ${item.value_rects.length} for the value`})
    )
  );
}

function placeTag(i) {
  document.querySelectorAll(".tag").forEach(t => t.remove());
  const item = ITEMS[i], bs = boxesOf.get(i);
  if (!bs || !bs.length) return;
  const c = containers[`${item.document}:${item.page}`];
  const x = Math.min(...item.rects.map(r => r.x)), y = Math.min(...item.rects.map(r => r.y));
  const bottom = Math.max(...item.rects.map(r => r.y + r.h));
  const tag = el("div", {class: "tag", text: `${item.field}  ->  ${show(item.value)}`.slice(0, 70), style: {"--c": COLOURS[item.verdict], left: x * 100 + "%"}});
  // Above the quote, or below it when the quote is at the very top of the page.
  if (y > 0.04) { tag.style.top = y * 100 + "%"; tag.style.transform = "translateY(calc(-100% - 6px))"; }
  else { tag.style.top = bottom * 100 + "%"; tag.style.transform = "translateY(6px)"; }
  c.appendChild(tag);
}

function select(i, scroll) {
  selected = i;
  boxesOf.forEach((bs, k) => bs.forEach(b => b.classList.toggle("selected", k === i)));
  placeTag(i);
  document.body.classList.add("has-selection");
  renderList();
  detail(ITEMS[i]);
  const bs = boxesOf.get(i);
  if (scroll && bs && bs.length) bs[0].scrollIntoView({block: "center", behavior: "smooth"});
}

document.getElementById("onlySel").addEventListener("change", e => document.getElementById("viewer").classList.toggle("only-selected", e.target.checked));
document.getElementById("noFill").addEventListener("change", e => document.getElementById("viewer").classList.toggle("hide-value", e.target.checked));
renderFilters(); renderList();
if (ITEMS.length) select(ITEMS.findIndex(i => i.verdict !== "verified") >= 0 ? ITEMS.findIndex(i => i.verdict !== "verified") : 0, false);
</script>
</body>
</html>
"""
