// Minimal, XSS-safe markdown renderer for chat messages.
//
// The wizard agent replies in markdown (headings, bold, lists, tables, code).
// Rendered as plain text it looks broken (raw `###`, `**`, `|`), so this turns
// a focused markdown subset into HTML. It is NOT a full CommonMark parser — it
// covers what the agent actually emits. Safety: every incoming character is
// HTML-escaped first, and only our own known tags are injected, so the output
// is safe to pass to `dangerouslySetInnerHTML`. Links go only to the web, mail
// or a place within the app (safeUrl), and one that leaves the app shows its
// host (linkHtml).

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function unescapeHtml(s: string): string {
  return s
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

function safeUrl(raw: string): string | null {
  const u = raw.trim();
  // Browsers read a backslash as a slash, so `/\\host` would leave the site too.
  if (u.includes("\\")) return null;
  if (/^https?:\/\//i.test(u) || /^mailto:/i.test(u)) return u;
  // `//host/path` is protocol-relative, not site-relative: it leaves the site
  // for a host the message author chose, so it is not in the allowlist.
  if (u.startsWith("//")) return null;
  if (u.startsWith("/") || u.startsWith("#")) return u;
  return null;
}

// Lucide's external-link icon, beside a link that leaves the wizard.
export const EXTERNAL_ICON =
  '<svg class="chat-link-icon" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>';

/**
 * A link, or null when its URL is not allowed. Both arguments are escaped
 * HTML. A link within the app (`/…`, `#…`) opens in the same tab. One that
 * leaves it opens in a new tab, says so with an icon, and shows its host after
 * the label, with the full address as its title: a friendly label repeated
 * from an uploaded document cannot hide where the link goes.
 */
function linkHtml(labelHtml: string, rawUrl: string): string | null {
  const url = safeUrl(rawUrl);
  if (!url) return null;
  if (!/^https?:/i.test(url)) return `<a href="${url}">${labelHtml}</a>`;
  let host: string;
  try {
    host = new URL(unescapeHtml(url)).host;
  } catch {
    return null;
  }
  if (!host) return null;
  // A bare address shows itself; repeating its host would say it twice. The
  // space sits inside the host's own box, so the link's underline stops at the
  // label; the gap on screen is the box's margin.
  const hostHtml =
    unescapeHtml(labelHtml) === unescapeHtml(url)
      ? ""
      : `<span class="chat-link-host"> ${escapeHtml(host.replace(/^www\./i, ""))}</span>`;
  return `<a href="${url}" target="_blank" rel="noreferrer noopener" title="${url}">${labelHtml}${EXTERNAL_ICON}${hostHtml}</a>`;
}

const LINK_START = /\[([^\]\n]+)\]\(/g;

// `[label](url)`. The URL ends at the first `)` that closes no `(` of its
// own, so `…/Foo_(bar))` keeps its parentheses; whitespace ends it too.
function replaceLinks(s: string, make: (label: string, url: string) => string): string {
  let out = "";
  let last = 0;
  LINK_START.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = LINK_START.exec(s))) {
    const start = m.index + m[0].length;
    let depth = 0;
    let end = -1;
    for (let j = start; j < s.length; j++) {
      const c = s[j];
      if (/\s/.test(c)) break;
      if (c === "(") depth++;
      else if (c === ")") {
        if (depth === 0) {
          end = j;
          break;
        }
        depth--;
      }
    }
    if (end <= start) continue;
    out += s.slice(last, m.index) + make(m[1], s.slice(start, end));
    last = end + 1;
    LINK_START.lastIndex = last;
  }
  return out + s.slice(last);
}

// A bare web address in the text. The text is escaped, so a quote or angle
// bracket after it is an entity, which ends it, as does a piece set aside.
const BARE_URL = /\bhttps?:\/\/(?:(?!&(?:lt|gt|quot);)[^\s\u0000])+/gi;

// Punctuation after an address belongs to the sentence, and so does a `)` that
// closes no `(` inside the address: "(see https://example.com/a)".
function trimUrl(url: string): string {
  let u = url;
  for (;;) {
    const lastChar = u[u.length - 1];
    if (lastChar && ".,;:!?*_'~".includes(lastChar)) {
      u = u.slice(0, -1);
      continue;
    }
    if (lastChar === ")" && (u.match(/\)/g) ?? []).length > (u.match(/\(/g) ?? []).length) {
      u = u.slice(0, -1);
      continue;
    }
    return u;
  }
}

function emphasis(s: string): string {
  return s
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
}

// Inline formatting. Input is already HTML-escaped. Code and links are set
// aside first, so nothing inside them is formatted: no link inside `code`, no
// emphasis inside an address. NUL marks a piece set aside; renderMarkdown
// takes NUL out of the input.
function inline(text: string): string {
  const kept: string[] = [];
  const keep = (html: string) => `\u0000${kept.push(html) - 1}\u0000`;
  let s = text.replace(/`([^`]+)`/g, (_m, c: string) => keep(`<code>${c}</code>`));
  s = replaceLinks(s, (label, url) => {
    const html = linkHtml(emphasis(label), url);
    return html ? keep(html) : label;
  });
  s = s.replace(BARE_URL, (match: string) => {
    const url = trimUrl(match);
    const html = linkHtml(url, url);
    return html ? keep(html) + match.slice(url.length) : match;
  });
  s = emphasis(s);
  // A link's label can hold code: pieces inside pieces come back in a second pass.
  for (let pass = 0; pass < 4 && s.includes("\u0000"); pass++) {
    s = s.replace(/\u0000(\d+)\u0000/g, (_m, i: string) => kept[Number(i)] ?? "");
  }
  return s;
}

function tableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((c) => c.trim());
}

const isTableSep = (line: string) => /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(line) && line.includes("-");

// A list item: its indentation, its number when it has one, its text.
const LIST_ITEM = /^(\s*)(?:[-*]|(\d{1,9})\.)\s+(.*)$/;

/** How much deeper than its parent an item stands to be a list under it. */
const NESTED = 2;

/** Lists inside lists, at most. */
const MAX_DEPTH = 6;

/**
 * The list that starts at `lines[at]`, and the index of the line after it.
 * Items of the same kind follow each other; an item indented under one (two
 * columns or more) starts a list inside that item, bulleted or numbered. So
 * a round of questions with the options under each stays one numbered list:
 * drawn as lists of their own, the options cut it into three that each
 * began at "1.".
 *
 * A numbered list begins at the number its first item has. Where something
 * at the margin does come between (a paragraph, bullets that are not
 * indented), the list after it goes on from its own number.
 */
function renderList(lines: string[], at: number, nested = false, depth = 0): [string, number] {
  const first = LIST_ITEM.exec(lines[at]);
  if (!first) return ["", at + 1];
  const base = first[1].length;
  const ordered = first[2] !== undefined;
  // A list inside an item ends at an item that stands further out than its
  // own first one; the item around it takes that one up as a list of its own.
  // At the margin, a first item that happens to be indented starts the list.
  const min = nested ? base : 0;
  const items: string[] = [];
  let i = at;
  while (i < lines.length) {
    const m = LIST_ITEM.exec(lines[i]);
    // Another kind of item at this level is another list.
    if (!m || (m[2] !== undefined) !== ordered || m[1].length < min) break;
    let item = inline(m[3].trim());
    i++;
    // Whatever is indented under the item is its own, down to MAX_DEPTH
    // levels; deeper items are drawn as items of the deepest list, so a long
    // staircase of indented lines cannot recurse without end.
    for (;;) {
      const under = i < lines.length ? LIST_ITEM.exec(lines[i]) : null;
      if (!under || under[1].length < base + NESTED || depth >= MAX_DEPTH) break;
      const [html, next] = renderList(lines, i, true, depth + 1);
      item += html;
      i = next;
    }
    items.push(`<li>${item}</li>`);
  }
  const tag = ordered ? "ol" : "ul";
  const start = ordered && Number(first[2]) !== 1 ? ` start="${Number(first[2])}"` : "";
  return [`<${tag}${start}>${items.join("")}</${tag}>`, i];
}

export function renderMarkdown(src: string): string {
  const lines = escapeHtml(src.replace(/\u0000/g, "")).replace(/\r\n?/g, "\n").split("\n");
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // fenced code block; its language (```mermaid) becomes a class, so the
    // chat can draw a diagram from it
    const fence = /^```\s*([A-Za-z0-9_+-]+)?/.exec(line.trim());
    if (fence) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i].trim())) {
        buf.push(lines[i]);
        i++;
      }
      i++; // skip closing fence
      const lang = fence[1] ? ` class="language-${fence[1].toLowerCase()}"` : "";
      out.push(`<pre><code${lang}>${buf.join("\n")}</code></pre>`);
      continue;
    }

    // table: header row + separator row
    if (line.includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const header = tableRow(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim() !== "") {
        rows.push(tableRow(lines[i]));
        i++;
      }
      const th = header.map((c) => `<th>${inline(c)}</th>`).join("");
      const trs = rows
        .map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`)
        .join("");
      out.push(
        `<div class="md-table-wrap"><table><thead><tr>${th}</tr></thead><tbody>${trs}</tbody></table></div>`,
      );
      continue;
    }

    // heading
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      const level = Math.min(h[1].length + 2, 6); // map # -> h3, keep chat modest
      out.push(`<h${level}>${inline(h[2].trim())}</h${level}>`);
      i++;
      continue;
    }

    // horizontal rule
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) {
      out.push("<hr>");
      i++;
      continue;
    }

    // unordered / ordered list
    if (LIST_ITEM.test(line)) {
      const [html, next] = renderList(lines, i);
      out.push(html);
      i = next;
      continue;
    }

    // blank line
    if (line.trim() === "") {
      i++;
      continue;
    }

    // paragraph: gather consecutive non-blank, non-special lines
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^```/.test(lines[i].trim()) &&
      !/^(#{1,6})\s+/.test(lines[i]) &&
      // The same test the list branch above uses: a line it does not take as
      // a list item (say "1234567890. id", past its nine digits) is text here.
      !LIST_ITEM.test(lines[i]) &&
      !(lines[i].includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1]))
    ) {
      para.push(inline(lines[i]));
      i++;
    }
    // Every branch above must take at least one line; should a later change
    // let them disagree again, the line is text rather than a loop that never ends.
    if (para.length === 0) {
      para.push(inline(lines[i]));
      i++;
    }
    out.push(`<p>${para.join("<br>")}</p>`);
  }

  return out.join("");
}
