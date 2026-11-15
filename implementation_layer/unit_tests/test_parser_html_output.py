"""The multimodal parser's HTML output keeps document markup and nothing else."""

import pytest

pytest.importorskip("markdown_it")

from gaik.software_components.parsers.multimodal_parser.html_allowlist import (  # noqa: E402
    keep_document_markup,
)
from gaik.software_components.parsers.multimodal_parser.multimodal_parser import (  # noqa: E402
    _markdown_to_html,
)


def test_a_table_with_spans_and_alignment_is_kept():
    table = (
        '<table><thead><tr><th colspan="2" style="text-align:right">Total</th></tr></thead>'
        '<tbody><tr><td rowspan="2">a &amp; b</td><td>1</td></tr></tbody></table>'
    )
    assert keep_document_markup(table) == (
        '<table><thead><tr><th colspan="2" style="text-align: right">Total</th></tr></thead>'
        '<tbody><tr><td rowspan="2">a &amp; b</td><td>1</td></tr></tbody></table>'
    )


def test_script_and_style_elements_are_removed_with_their_content():
    out = keep_document_markup("<p>before</p><script>run()</script><style>p{}</style><p>after</p>")
    assert out == "<p>before</p><p>after</p>"


def test_tags_outside_the_list_leave_their_text_only():
    out = keep_document_markup(
        '<p>see <img src="https://example.com/x.png" alt="x"><form>a</form></p>'
    )
    assert out == "<p>see a</p>"


def test_attributes_outside_the_list_are_dropped():
    out = keep_document_markup(
        '<p onclick="go()" class="c" id="i">text</p><td style="color:red">1</td>'
    )
    assert out == "<p>text</p><td>1</td>"


@pytest.mark.parametrize(
    ("href", "kept"),
    [
        ("https://example.com/a?b=1&c=2", True),
        ("mailto:someone@example.com", True),
        ("#section-2", True),
        ("notes/page.html", True),
        ("javascript:go()", False),
        ("  JaVa\tScRiPt:go()", False),
        ("data:text/html,hello", False),
        ("//example.com/other", False),
    ],
)
def test_links_keep_only_web_and_mail_addresses(href, kept):
    out = keep_document_markup(f'<a href="{href}">link</a>')
    assert ("href=" in out) is kept
    assert out.endswith(">link</a>")


def test_text_that_looks_like_markup_stays_text():
    out = keep_document_markup("<p>&lt;script&gt;x&lt;/script&gt; 1 &lt; 2</p>")
    assert out == "<p>&lt;script&gt;x&lt;/script&gt; 1 &lt; 2</p>"


def test_unclosed_tags_are_closed():
    assert keep_document_markup("<ul><li>one<li>two") == "<ul><li>one<li>two</li></li></ul>"


def test_the_rendered_page_keeps_markdown_and_tables_but_not_scripts():
    md = (
        "# Invoice\n\nSome **bold** text and a [link](https://example.com).\n\n"
        "<table><tr><td>1</td></tr></table>\n\n"
        '<script>run()</script>\n\n<a href="javascript:go()">x</a>\n'
    )
    page = _markdown_to_html(md, title="doc")
    assert "<h1>Invoice</h1>" in page
    assert "<strong>bold</strong>" in page
    assert '<a href="https://example.com">link</a>' in page
    assert "<td>1</td>" in page
    assert "<script>" not in page and "run()" not in page
    assert "javascript:" not in page
    # The page's own head is untouched.
    assert "<style>" in page and "<title>doc</title>" in page


@pytest.mark.parametrize("void", ["embed", "frame"])
def test_a_dropped_void_element_does_not_hide_what_follows(void):
    out = keep_document_markup(f'<p>before</p><{void} src="https://example.com/x"><p>after</p>')
    assert out == "<p>before</p><p>after</p>"


def test_an_end_tag_also_closes_a_dropped_element_left_open_inside_it():
    out = keep_document_markup(
        "<p>before</p><object><applet>fallback</object><p>after</p><embed><p>end</p>"
    )
    assert out == "<p>before</p><p>after</p><p>end</p>"


@pytest.mark.parametrize(
    "page",
    [
        # In HTML, a title's content is text: "</head>" in it does not close it,
        "<head><title>Report </head> title only</title></head><p>body</p>",
        # and neither does a start tag in it open anything.
        "<head><title><svg>Report </head> title only</svg></title></head><p>body</p>",
    ],
)
def test_a_tag_inside_a_text_only_element_is_text(page):
    assert keep_document_markup(page) == "<p>body</p>"


@pytest.mark.parametrize("inner", ["select", "template"])
def test_an_end_tag_does_not_close_a_select_or_template_left_open_inside(inner):
    # A browser ignores other end tags inside them.
    page = f"<object><{inner}>x</object>more</{inner}></object><p>after</p>"
    assert keep_document_markup(page) == "<p>after</p>"
