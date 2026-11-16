"""Keep the document markup a parsed page needs and drop everything else.

The model writes tables as HTML and the rest as Markdown, so the HTML output
renders both. Rendered HTML goes through :func:`keep_document_markup`, which
rebuilds it from parsed tags: only the tags and attributes listed here are
written back, all text is escaped again, links keep only http, https and mailto
addresses, the content of script, style and similar elements is removed, and an
image leaves its alt text. A dropped element that is never closed gives back
what it swallowed as text.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

ALLOWED_TAGS = frozenset(
    """a abbr b blockquote br caption code col colgroup dd del div dl dt em
    h1 h2 h3 h4 h5 h6 hr i ins kbd li mark ol p pre q s small span strong sub sup
    table tbody td tfoot th thead tr u ul""".split()
)
VOID_TAGS = frozenset({"br", "col", "hr"})
# Elements whose content is dropped along with the tag.
DROPPED_WITH_CONTENT = frozenset(
    """script style iframe frame frameset object embed applet template noscript
    noembed noframes textarea select title svg math head""".split()
)
# Void elements in that list: they have no end tag and no content, so they are
# dropped on their own instead of waiting for an end tag that never comes.
_DROPPED_VOID = frozenset({"embed", "frame"})
# Elements whose content is text only (HTML's raw text and escapable raw text
# elements): another element's end tag inside them is text, so only their own
# end tag closes them.
_TEXT_ONLY = frozenset(
    {"script", "style", "iframe", "noembed", "noframes", "noscript", "textarea", "title"}
)
# Dropped elements that an ancestor's end tag does not close: the text-only ones,
# and select and template, in which a browser ignores other end tags.
_OWN_END_TAG_ONLY = _TEXT_ONLY | {"select", "template"}

_CELL_ATTRS = {"colspan", "rowspan", "style"}
ALLOWED_ATTRS: dict[str, set[str]] = {
    "a": {"href", "title"},
    "abbr": {"title"},
    "col": {"span"},
    "colgroup": {"span"},
    "div": {"data-bbox", "data-label"},
    "ol": {"start"},
    "td": _CELL_ATTRS,
    "th": _CELL_ATTRS | {"scope"},
}

_NUMBER_ATTRS = {"colspan", "rowspan", "span", "start"}
_SCOPE_VALUES = {"row", "col", "rowgroup", "colgroup"}
_TEXT_ALIGN_RE = re.compile(r"^\s*text-align\s*:\s*(left|right|center)\s*;?\s*$", re.IGNORECASE)
_LINK_SCHEMES = ("http:", "https:", "mailto:")
_CONTROL_RE = re.compile(r"[\x00-\x20\x7f]+")


def _attr_value(tag: str, name: str, value: str | None) -> str | None:
    """The value to keep for an allowed attribute, or None to drop it."""
    if value is None:
        return None
    if name in _NUMBER_ATTRS:
        return value.strip() if value.strip().isdigit() and len(value.strip()) <= 4 else None
    if name == "scope":
        return value.strip().lower() if value.strip().lower() in _SCOPE_VALUES else None
    if name == "style":
        match = _TEXT_ALIGN_RE.match(value)
        return f"text-align: {match.group(1).lower()}" if match else None
    if name == "href":
        compact = _CONTROL_RE.sub("", value).lower()
        if compact.startswith("#"):
            return value.strip()
        if ":" in compact.split("/", 1)[0] and not compact.startswith(_LINK_SCHEMES):
            return None
        if compact.startswith("//"):
            return None
        return value.strip()
    return value


class _Rebuilder(HTMLParser):
    def __init__(self, source: str, out: list[str], open_tags: list[str]) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.out = out
        self.open = open_tags
        self.dropping: list[str] = []
        # Where the outermost dropped element began: the output length, the open
        # tags and the source offset after its start tag. If it is never closed,
        # the rest of the source is rebuilt from there without it.
        self.drop_start: tuple[int, list[str], int] | None = None
        # Computed once per pass, so each start tag costs one lookup.
        self.line_starts = [0] + [m.end() for m in re.finditer("\n", source)]
        lowered = source.lower()
        self.last_end = {t: lowered.rfind(f"</{t}") for t in DROPPED_WITH_CONTENT}
        # Set when a text-only start tag was dropped on its own: the parser must
        # not then read what follows as that element's text.
        self.skip_text_mode = False

    def set_cdata_mode(self, *args, **kwargs) -> None:
        if self.skip_text_mode:
            self.skip_text_mode = False
            return
        super().set_cdata_mode(*args, **kwargs)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.skip_text_mode = False
        if tag in _DROPPED_VOID:
            return
        if self.dropping:
            # Inside a text-only element a start tag is text, so nothing is pushed
            # above it and only its own end tag closes it.
            if tag in DROPPED_WITH_CONTENT and self.dropping[-1] not in _TEXT_ONLY:
                self.dropping.append(tag)
            return
        if tag in DROPPED_WITH_CONTENT:
            line, col = self.getpos()
            # getpos() counts lines by "\n" only.
            offset = self.line_starts[line - 1] + col + len(self.get_starttag_text() or "")
            if self.last_end[tag] < offset:
                # No end tag follows, so the element can never close: drop only
                # its start tag now instead of rebuilding the rest in a new pass.
                self.skip_text_mode = tag in _TEXT_ONLY
                return
            self.dropping.append(tag)
            self.drop_start = (len(self.out), list(self.open), offset)
            return
        if tag == "img":
            # An image is not kept, but its alt text is, as in the Word export.
            alt = dict(attrs).get("alt")
            if alt and alt.strip():
                self.out.append(html.escape(alt.strip(), quote=False))
            return
        if tag not in ALLOWED_TAGS:
            return
        kept = []
        allowed = ALLOWED_ATTRS.get(tag, set())
        for name, value in attrs:
            if name in allowed:
                clean = _attr_value(tag, name, value)
                if clean is not None:
                    kept.append(f' {name}="{html.escape(clean, quote=True)}"')
        self.out.append(f"<{tag}{''.join(kept)}>")
        if tag not in VOID_TAGS:
            self.open.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in VOID_TAGS or tag == "img":
            self.handle_starttag(tag, attrs)
        # Any other self-closed tag is dropped; it has no content to keep.

    def handle_endtag(self, tag: str) -> None:
        if self.dropping:
            if tag == self.dropping[-1]:
                self.dropping.pop()
            elif tag in self.dropping:
                # Close back to the matching element: a dropped element left open
                # inside it ends with it, as a browser would end it, unless one of
                # them ends only with its own end tag.
                at = len(self.dropping) - 1 - self.dropping[::-1].index(tag)
                if not _OWN_END_TAG_ONLY.intersection(self.dropping[at + 1 :]):
                    del self.dropping[at:]
            return
        if tag not in self.open:
            return
        while self.open:
            last = self.open.pop()
            self.out.append(f"</{last}>")
            if last == tag:
                break

    def handle_data(self, data: str) -> None:
        if not self.dropping:
            self.out.append(html.escape(data, quote=False))

    def close(self) -> None:
        super().close()
        while self.open:
            self.out.append(f"</{self.open.pop()}>")


def keep_document_markup(fragment: str) -> str:
    """Return ``fragment`` rebuilt with only the allowed tags, attributes and links."""
    out: list[str] = []
    open_tags: list[str] = []
    while True:
        rebuilder = _Rebuilder(fragment, out, open_tags)
        rebuilder.feed(fragment)
        if not (rebuilder.dropping and rebuilder.drop_start):
            rebuilder.close()
            return "".join(rebuilder.out)
        # A dropped element that is never closed did not hold the rest of the
        # page: drop only its start tag and rebuild what follows it.
        out_len, open_tags, offset = rebuilder.drop_start
        out = rebuilder.out[:out_len]
        fragment = fragment[offset:]
