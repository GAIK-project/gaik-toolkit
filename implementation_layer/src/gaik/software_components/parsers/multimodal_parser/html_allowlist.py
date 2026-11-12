"""Keep the document markup a parsed page needs and drop everything else.

The model writes tables as HTML and the rest as Markdown, so the HTML output
renders both. Rendered HTML goes through :func:`keep_document_markup`, which
rebuilds it from parsed tags: only the tags and attributes listed here are
written back, all text is escaped again, links keep only http, https and mailto
addresses, and the content of script, style and similar elements is removed.
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
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.open: list[str] = []
        self.dropping: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.dropping:
            if tag in DROPPED_WITH_CONTENT:
                self.dropping.append(tag)
            return
        if tag in DROPPED_WITH_CONTENT:
            self.dropping.append(tag)
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
        if tag in VOID_TAGS:
            self.handle_starttag(tag, attrs)
        # Any other self-closed tag is dropped; it has no content to keep.

    def handle_endtag(self, tag: str) -> None:
        if self.dropping:
            if tag == self.dropping[-1]:
                self.dropping.pop()
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
    rebuilder = _Rebuilder()
    rebuilder.feed(fragment)
    rebuilder.close()
    return "".join(rebuilder.out)
