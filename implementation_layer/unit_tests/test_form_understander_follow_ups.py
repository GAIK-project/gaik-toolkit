"""FormUnderstander follow-ups (#299 items 3 and 4): repeated ids are found in one pass,
and joiners that change what is shown are kept, so ``changed`` is truthful."""

import time

import pytest
from gaik.software_components.form_understander import FormUnderstander
from gaik.software_components.form_understander.understander import LabelMapping

SCIENTIST = "\U0001f469‍\U0001f52c"  # woman scientist, one emoji
TWO_EMOJI = "\U0001f469\U0001f52c"  # woman, microscope
PERSIAN = "می‌خواهم"  # "mi-khaham", ZWNJ inside
PERSIAN_JOINED = PERSIAN.replace("‌", "")


class _Provider:
    provider, model, raw = "google", "m", None

    def __init__(self, entries):
        self.entries = entries
        self.calls = 0

    def chat_parsed(self, **kwargs):
        self.calls += 1
        return LabelMapping.model_validate({"entries": self.entries})

    def chat(self, *a, **k):
        raise AssertionError

    def chat_stream(self, *a, **k):
        raise AssertionError

    def embed(self, *a, **k):
        raise AssertionError


def _form(monkeypatch, entries):
    from gaik.software_components.llm import factory

    client = _Provider(entries)
    monkeypatch.setattr(factory, "create_llm_client", lambda config: client)
    return FormUnderstander({"provider": "google", "model": "m"}), client


@pytest.mark.parametrize(
    "label",
    [
        SCIENTIST,
        "\U0001f3f3️‍\U0001f308",  # rainbow flag
        "\U0001f468\U0001f3fd‍\U0001f4bb",  # man technologist, skin tone
        "ශ්‍රී",  # Sinhala "shri" with its ZWJ
        "ന്‍",  # Malayalam chillu written with a ZWJ at the end
        PERSIAN,
    ],
)
def test_a_joiner_that_changes_what_is_shown_comes_back(monkeypatch, label):
    form, _ = _form(monkeypatch, [{"id": "a", "label": label}])

    (described,) = form.describe_labels([{"id": "a", "raw": label}])

    assert described.label == label
    assert described.original == label
    assert described.changed is False
    assert form.clean_labels([{"id": "a", "raw": label}]) == {"a": label}


@pytest.mark.parametrize(
    ("page", "model"),
    [(SCIENTIST, TWO_EMOJI), (TWO_EMOJI, SCIENTIST), (PERSIAN, PERSIAN_JOINED)],
)
def test_a_label_that_lost_or_gained_a_joiner_is_a_change(monkeypatch, page, model):
    form, _ = _form(monkeypatch, [{"id": "a", "label": model}])

    (described,) = form.describe_labels([{"id": "a", "raw": page}])

    assert described.changed is True
    assert (described.label, described.original) == (model, page)


def test_a_non_joiner_outside_letters_is_still_taken_out(monkeypatch):
    form, _ = _form(monkeypatch, [{"id": "a", "label": "‌Name‌ 1‌2"}])

    (described,) = form.describe_labels([{"id": "a", "raw": "Name 12"}])

    assert described.label == "Name 12"
    assert described.changed is False


def test_bidi_controls_are_still_taken_out_next_to_a_joiner(monkeypatch):
    form, _ = _form(monkeypatch, [{"id": "a", "label": f"‮{SCIENTIST}‬"}])

    (described,) = form.describe_labels([{"id": "a", "raw": SCIENTIST}])

    assert described.label == SCIENTIST
    assert described.changed is False


def test_repeated_ids_are_named_in_order(monkeypatch):
    form, client = _form(monkeypatch, [])
    fields = [{"id": i, "raw": "x"} for i in ("b", "a", "b", "c", "a", "b")]

    with pytest.raises(ValueError, match=r"repeated: \['a', 'b'\]"):
        form.describe_labels(fields)
    assert client.calls == 0


def test_many_fields_are_checked_for_repeated_ids_quickly(monkeypatch):
    form, client = _form(monkeypatch, [])
    fields = [{"id": f"f{i}", "raw": "x"} for i in range(20_000)] + [{"id": "f7", "raw": "y"}]

    started = time.perf_counter()
    with pytest.raises(ValueError, match=r"repeated: \['f7'\]"):
        form.describe_labels(fields)
    # A scan per field took seconds for this many; one pass takes milliseconds.
    assert time.perf_counter() - started < 1.0
    assert client.calls == 0
