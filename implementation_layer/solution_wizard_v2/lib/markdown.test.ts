import { describe, expect, it } from "vitest";
import { renderMarkdown } from "@/lib/markdown";

/**
 * The agent's reply is model output, and `chat-panel.tsx` hands the result of
 * renderMarkdown() straight to `dangerouslySetInnerHTML`. That makes this the
 * one path from generated text into the DOM, so the escaping and the link
 * allowlist are pinned down here first, formatting second.
 */
describe("renderMarkdown — safety", () => {
  it("escapes HTML instead of emitting it", () => {
    const html = renderMarkdown("<script>alert(1)</script>");
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });

  it("escapes HTML inside a fenced code block", () => {
    const html = renderMarkdown("```\n<img src=x onerror=alert(1)>\n```");
    expect(html).toContain("<pre><code>");
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img src=x onerror=alert(1)&gt;");
  });

  it("keeps a fence's language as a class, so a mermaid block can become a diagram", () => {
    const html = renderMarkdown("```mermaid\nflowchart TD\n  a --> b\n```");
    expect(html).toContain('<pre><code class="language-mermaid">flowchart TD');
    expect(html).toContain("a --&gt; b");
  });

  it("puts nothing but letters, digits and -_+ of a fence's language into the class", () => {
    const html = renderMarkdown('```"onmouseover=alert(1)\nx\n```');
    expect(html).toContain("<pre><code>x</code></pre>");
    expect(html).not.toContain("onmouseover=alert(1)\"");
  });

  it.each([
    ["javascript:", "[click](javascript:alert(1))"],
    ["mixed-case javascript:", "[click](JaVaScRiPt:alert(1))"],
    ["data:", "[click](data:text/html,<script>alert(1)</script>)"],
    ["vbscript:", "[click](vbscript:msgbox(1))"],
    ["protocol-relative", "[click](//evil.example/x)"],
    ["backslash after the slash", "[click](/\\\\other.example/x)"],
  ])("does not linkify a %s URL — the label is kept as text", (_name, src) => {
    const html = renderMarkdown(src);
    expect(html).not.toContain("<a ");
    expect(html).toContain("click");
  });

  it("keeps a quote in a URL escaped, so it cannot break out of href", () => {
    // No space, so the link regex still matches — the escape pass is what
    // stops `onmouseover=` from becoming its own attribute.
    const html = renderMarkdown('[x](https://example.com"onmouseover=alert(1))');
    expect(html).toContain("&quot;");
    expect(html).not.toContain('"onmouseover');
  });

  it("escapes the link label", () => {
    const html = renderMarkdown("[<b>bold</b>](https://example.com)");
    expect(html).toContain("&lt;b&gt;");
    expect(html).not.toContain("<b>");
  });

  it.each([
    ["https", "https://example.com"],
    ["http", "http://example.com"],
    ["mailto", "mailto:someone@example.com"],
    ["root-relative", "/sessions/abc"],
    ["anchor", "#section"],
  ])("allows a %s link", (_name, url) => {
    const html = renderMarkdown(`[label](${url})`);
    expect(html).toContain(`href="${url}"`);
    // An external link's icon and host follow its label inside the link.
    expect(html).toMatch(/">label(<svg [^]*)?<\/a>/);
  });

  it("opens external links without leaking the referrer or the opener", () => {
    const html = renderMarkdown("[label](https://example.com)");
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noreferrer noopener"');
  });

  it("does not linkify a bare address it would not allow in a link", () => {
    for (const src of ["javascript:alert(1)", "//evil.example/x", "see https:// here"]) {
      expect(renderMarkdown(src)).not.toContain("<a ");
    }
  });

  it("keeps a quote after a bare address out of the link", () => {
    const html = renderMarkdown('"https://example.com"onmouseover=alert(1)');
    expect(html).toContain('href="https://example.com"');
    expect(html).not.toContain('"onmouseover');
  });

  it("drops NUL from the input, so it cannot forge a piece set aside", () => {
    const html = renderMarkdown("a \u00000\u0000 b `c`");
    expect(html).toBe("<p>a 0 b <code>c</code></p>");
  });
});

describe("renderMarkdown — links", () => {
  it.each([
    ["root-relative", "/sessions/abc?tab=poc"],
    ["anchor", "#gate"],
  ])("opens a %s link in the same tab, with no external marks", (_name, url) => {
    const html = renderMarkdown(`[PoC](${url})`);
    expect(html).toBe(`<p><a href="${url}">PoC</a></p>`);
  });

  it("opens a mail link in place", () => {
    expect(renderMarkdown("[mail](mailto:a@example.com)")).toBe('<p><a href="mailto:a@example.com">mail</a></p>');
  });

  it("marks an external link with an icon and its host, and titles it with the whole address", () => {
    const html = renderMarkdown("[GAIK-dokumentaatio](https://www.gaik.ai/docs?a=1&b=2)");
    expect(html).toContain('href="https://www.gaik.ai/docs?a=1&amp;b=2"');
    expect(html).toContain('title="https://www.gaik.ai/docs?a=1&amp;b=2"');
    expect(html).toMatch(/GAIK-dokumentaatio<svg class="chat-link-icon"[^>]*aria-hidden="true"/);
    expect(html).toContain('<span class="chat-link-host"> gaik.ai</span></a>');
  });

  it("shows the host a friendly label would hide", () => {
    const html = renderMarkdown("[Your bank](https://login.evil.example/bank)");
    expect(html).toContain('<span class="chat-link-host"> login.evil.example</span>');
  });

  it("links a bare https address without repeating its host", () => {
    const html = renderMarkdown("Katso https://example.com/ohje.");
    expect(html).toContain('<a href="https://example.com/ohje" target="_blank"');
    expect(html).toContain("https://example.com/ohje<svg");
    expect(html).not.toContain("chat-link-host");
    // The full stop belongs to the sentence.
    expect(html).toMatch(/<\/a>\.<\/p>$/);
  });

  it("ends a bare address at a closing parenthesis it did not open", () => {
    const html = renderMarkdown("(lisää: https://example.com/a)");
    expect(html).toContain('href="https://example.com/a"');
    expect(html).toMatch(/<\/a>\)<\/p>$/);
    expect(renderMarkdown("https://en.wikipedia.org/wiki/Foo_(bar)")).toContain(
      'href="https://en.wikipedia.org/wiki/Foo_(bar)"',
    );
  });

  it("keeps balanced parentheses in a link's address", () => {
    const html = renderMarkdown("[Foo](https://en.wikipedia.org/wiki/Foo_(bar)) jatkuu");
    expect(html).toContain('href="https://en.wikipedia.org/wiki/Foo_(bar)"');
    expect(html).toMatch(/<\/a> jatkuu<\/p>$/);
    expect(html).not.toContain(")</a>)");
  });

  it("puts no emphasis inside a link's address", () => {
    const html = renderMarkdown("[a](https://example.com/*x*/y) and *after*");
    expect(html).toContain('href="https://example.com/*x*/y"');
    expect(html).toContain("<em>after</em>");
    expect(html).not.toContain("<em>x</em>");
  });

  it("still formats a link's label", () => {
    expect(renderMarkdown("[**tärkeä**](/sessions/a)")).toBe('<p><a href="/sessions/a"><strong>tärkeä</strong></a></p>');
  });

  it("makes no link inside inline code", () => {
    expect(renderMarkdown("`[x](https://example.com)`")).toBe("<p><code>[x](https://example.com)</code></p>");
    expect(renderMarkdown("`https://example.com`")).toBe("<p><code>https://example.com</code></p>");
  });

  it("does not link the same address twice", () => {
    const html = renderMarkdown("[https://example.com](https://example.com)");
    expect(html.match(/<a /g)).toHaveLength(1);
    expect(html).not.toContain("chat-link-host");
  });
});

describe("renderMarkdown — formatting", () => {
  it("ends on a line that starts with a number too long to be a list item", () => {
    // Ten digits and a dot: no list item (at most nine digits), so a paragraph.
    expect(renderMarkdown("1234567890. tilaus")).toBe("<p>1234567890. tilaus</p>");
    expect(renderMarkdown("Tilaukset:\n12345678901. ensimmäinen\n2. toinen")).toContain(
      "12345678901. ensimmäinen",
    );
  });

  it("renders headings two levels down, capped at h6", () => {
    expect(renderMarkdown("# Title")).toBe("<h3>Title</h3>");
    expect(renderMarkdown("#### Deep")).toBe("<h6>Deep</h6>");
    expect(renderMarkdown("###### Deepest")).toBe("<h6>Deepest</h6>");
  });

  it("renders bold, italic and inline code", () => {
    expect(renderMarkdown("**bold**")).toContain("<strong>bold</strong>");
    expect(renderMarkdown("*italic*")).toContain("<em>italic</em>");
    expect(renderMarkdown("`code`")).toContain("<code>code</code>");
  });

  it("keeps a round of questions one numbered list, with each question's options inside its item", () => {
    // The options used to end the numbered list, so every question was "1.".
    expect(renderMarkdown("1. Q\n   - a\n   - b\n2. Q\n   - c\n3. Q")).toBe(
      "<ol><li>Q<ul><li>a</li><li>b</li></ul></li><li>Q<ul><li>c</li></ul></li><li>Q</li></ol>",
    );
  });

  it("nests a numbered list under a bullet, and goes back out to the outer list", () => {
    expect(renderMarkdown("- a\n  1. x\n  2. y\n- b")).toBe(
      "<ul><li>a<ol><li>x</li><li>y</li></ol></li><li>b</li></ul>",
    );
    expect(renderMarkdown("1. a\n   - x\n     - deep\n2. b")).toBe(
      "<ol><li>a<ul><li>x<ul><li>deep</li></ul></li></ul></li><li>b</li></ol>",
    );
  });

  it("a numbered list that goes on after something at the margin keeps its own number", () => {
    // Bullets at the margin are a list of their own; the question after them is still the second.
    expect(renderMarkdown("1. Q\n- a\n- b\n2. Q")).toBe(
      '<ol><li>Q</li></ol><ul><li>a</li><li>b</li></ul><ol start="2"><li>Q</li></ol>',
    );
    expect(renderMarkdown("1. one\n\nBetween.\n\n2. two\n3. three")).toBe(
      '<ol><li>one</li></ol><p>Between.</p><ol start="2"><li>two</li><li>three</li></ol>',
    );
    // Only digits reach the attribute.
    expect(renderMarkdown('7. "><b>x')).toBe('<ol start="7"><li>&quot;&gt;&lt;b&gt;x</li></ol>');
  });

  it("an item less indented than a nested list's first item is not drawn at its depth", () => {
    // c stands between a and b: it is a's, not b's sibling.
    expect(renderMarkdown("- a\n    - b\n  - c")).toBe(
      "<ul><li>a<ul><li>b</li></ul><ul><li>c</li></ul></li></ul>",
    );
  });

  it("a long staircase of indented items stops nesting and still ends", () => {
    const lines = Array.from({ length: 3000 }, (_, i) => `${" ".repeat(i * 2)}- level ${i}`);
    const html = renderMarkdown(lines.join("\n"));
    expect(html).toContain("level 2999");
    expect(html.split("<ul>").length - 1).toBeLessThanOrEqual(7);
  });

  it("items of one kind are one list whatever their indentation at the start", () => {
    expect(renderMarkdown("  - one\n- two")).toBe("<ul><li>one</li><li>two</li></ul>");
    expect(renderMarkdown(" 1. one\n2. two")).toBe("<ol><li>one</li><li>two</li></ol>");
  });

  it("renders an unordered and an ordered list", () => {
    expect(renderMarkdown("- one\n- two")).toBe("<ul><li>one</li><li>two</li></ul>");
    expect(renderMarkdown("1. one\n2. two")).toBe("<ol><li>one</li><li>two</li></ol>");
  });

  it("renders a table inside its scroll wrapper", () => {
    const html = renderMarkdown("| a | b |\n|---|---|\n| 1 | 2 |");
    expect(html).toContain('<div class="md-table-wrap">');
    expect(html).toContain("<th>a</th><th>b</th>");
    expect(html).toContain("<tr><td>1</td><td>2</td></tr>");
  });

  it("renders a horizontal rule", () => {
    expect(renderMarkdown("---")).toBe("<hr>");
  });

  it("joins the lines of one paragraph with a line break", () => {
    expect(renderMarkdown("first\nsecond")).toBe("<p>first<br>second</p>");
  });

  it("starts a new paragraph after a blank line", () => {
    expect(renderMarkdown("first\n\nsecond")).toBe("<p>first</p><p>second</p>");
  });

  it("normalises CRLF input", () => {
    expect(renderMarkdown("first\r\n\r\nsecond")).toBe("<p>first</p><p>second</p>");
  });

  it("returns an empty string for empty or blank input", () => {
    expect(renderMarkdown("")).toBe("");
    expect(renderMarkdown("\n\n")).toBe("");
  });
});
