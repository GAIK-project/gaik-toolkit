"""An unclosed dropped element and an image in the multimodal parser's HTML output."""

import pytest
from gaik.software_components.parsers.multimodal_parser.html_allowlist import (
    keep_document_markup,
)


@pytest.mark.parametrize("tag", ["title", "select", "textarea", "script", "svg"])
def test_unclosed_dropped_element_keeps_the_text_after_it(tag):
    out = keep_document_markup(f"<p>Before <{tag}> tag</p><p>Next paragraph & more</p>")
    assert "Before" in out
    assert "Next paragraph &amp; more" in out
    assert f"<{tag}" not in out


def test_closed_dropped_element_still_drops_its_content():
    out = keep_document_markup("<p>a</p><script>alert(1)</script><title>T</title><p>b</p>")
    assert "alert" not in out and "T" not in out
    assert out == "<p>a</p><p>b</p>"


def test_what_follows_an_unclosed_script_still_goes_through_the_allowlist():
    out = keep_document_markup('<p>x</p><script><b onclick="go()">bold</b><iframe>y</iframe>')
    assert out == "<p>x</p><b>bold</b>"


@pytest.mark.parametrize(
    "fragment",
    ['<img alt="Figure 1: site map" src="a.png">', '<img src="a.png" alt="Figure 1: site map"/>'],
)
def test_image_leaves_its_alt_text(fragment):
    out = keep_document_markup(f"<p>{fragment}</p>")
    assert out == "<p>Figure 1: site map</p>"


def test_image_alt_text_is_escaped_and_empty_alt_gives_nothing():
    escaped = "&lt;script&gt;x&lt;/script&gt;"
    assert keep_document_markup('<img alt="<script>x</script>">') == escaped
    assert keep_document_markup('<img alt="" src="a.png"><img src="b.png">') == ""


def test_unclosed_title_in_markdown_keeps_the_next_paragraph_as_markup():
    out = keep_document_markup("<p>Use the <title> tag.</p>\n<p>Next</p>\n<p>Last</p>")
    assert out == "<p>Use the  tag.</p>\n<p>Next</p>\n<p>Last</p>"


def test_two_unclosed_dropped_elements_on_later_lines():
    out = keep_document_markup("<p>a</p>\r\n<p>b<select>\n<option>c</p>\n<p>d<textarea>e</p>")
    assert out == "<p>a</p>\r\n<p>b\nc</p>\n<p>de</p>"
