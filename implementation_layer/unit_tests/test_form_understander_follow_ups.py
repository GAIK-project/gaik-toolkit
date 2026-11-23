"""FormUnderstander follow-ups (#299 items 3 and 4): repeated ids are found in one pass,
and joiners that change what is shown are kept, so ``changed`` is truthful."""

import time

import pytest
from gaik.software_components.form_understander import FormUnderstander
from gaik.software_components.form_understander.understander import LabelMapping

SCIENTIST = "\U0001f469\u200d\U0001f52c"  # woman scientist, one emoji
TWO_EMOJI = "\U0001f469\U0001f52c"  # woman, microscope
PERSIAN = "می\u200cخواهم"  # "mi-khaham", ZWNJ inside
PERSIAN_JOINED = PERSIAN.replace("\u200c", "")


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
        "\U0001f3f3\ufe0f\u200d\U0001f308",  # rainbow flag
        "\U0001f468\U0001f3fd\u200d\U0001f4bb",  # man technologist, skin tone
        "ශ්\u200dරී",  # Sinhala "shri" with its ZWJ
        "\u0d28\u0d4d\u200d",  # Malayalam chillu: ZWJ after a virama
        "\u0d05\u0d35\u0d28\u0d4d\u200d \u0d35\u0d28\u0d4d\u0d28\u0d41",  # its ZWJ before a space
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


ZWJ, ZWNJ = "\u200d", "\u200c"


@pytest.mark.parametrize(
    ("page", "shown"),
    [
        (f"Name{ZWJ}", "Name"),
        (f"{ZWJ}Name", "Name"),
        (f"First{ZWJ} Name", "First Name"),
        (f"First {ZWNJ}Name", "First Name"),
        (f"{SCIENTIST}{ZWJ}", SCIENTIST),
    ],
)
def test_a_joiner_at_an_edge_or_beside_a_space_is_taken_out(monkeypatch, page, shown):
    form, _ = _form(monkeypatch, [])

    (described,) = form.describe_labels([{"id": "a", "raw": page}])

    assert (described.label, described.original) == (shown, shown)
    assert described.changed is False


@pytest.mark.parametrize("answer", [ZWJ, f"{ZWJ} ", f" {ZWNJ}{ZWJ} ", "\u0301"])
def test_a_label_that_shows_nothing_keeps_the_page_label(monkeypatch, answer):
    form, _ = _form(monkeypatch, [{"id": "a", "label": answer}])

    (described,) = form.describe_labels([{"id": "a", "raw": "Etunimi"}])

    assert (described.label, described.changed) == ("Etunimi", False)
    assert form.clean_labels([{"id": "a", "raw": "Etunimi"}]) == {}


def test_a_cut_leaves_no_joiner_at_its_end(monkeypatch):
    page = "x" * 58 + SCIENTIST + " tail"  # the cut falls just after the joiner
    form, _ = _form(monkeypatch, [{"id": "a", "label": page}])

    (described,) = form.describe_labels([{"id": "a", "raw": page}])

    assert not described.label.endswith(ZWJ)
    assert described.truncated is True and described.changed is False


def test_a_non_joiner_outside_letters_is_still_taken_out(monkeypatch):
    form, _ = _form(monkeypatch, [{"id": "a", "label": "\u200cName\u200c 1\u200c2"}])

    (described,) = form.describe_labels([{"id": "a", "raw": "Name 12"}])

    assert described.label == "Name 12"
    assert described.changed is False


def test_bidi_controls_are_still_taken_out_next_to_a_joiner(monkeypatch):
    form, _ = _form(monkeypatch, [{"id": "a", "label": f"\u202e{SCIENTIST}\u202c"}])

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


# ── Retries (#146 item 10) ──────────────────────────────────────────


def _status_error(status):
    import httpx
    import openai

    request = httpx.Request("POST", "https://api.example.test/v1/chat/completions")
    response = httpx.Response(status, request=request)
    cls = openai.BadRequestError if status == 400 else openai.RateLimitError
    return cls("x", response=response, body=None)


def _failing_form(monkeypatch, failures):
    from gaik.software_components.llm import retries

    form, client = _form(monkeypatch, [{"id": "a", "label": "Etunimi"}])
    waits = []
    monkeypatch.setattr(retries.time, "sleep", waits.append)
    answer = client.chat_parsed

    def chat_parsed(**kwargs):
        if failures:
            client.calls += 1
            raise failures.pop(0)
        return answer(**kwargs)

    client.chat_parsed = chat_parsed
    return form, client, waits


def test_a_bad_request_is_not_sent_again(monkeypatch):
    import openai

    form, client, waits = _failing_form(monkeypatch, [_status_error(400)])

    with pytest.raises(openai.BadRequestError):
        form.clean_labels([{"id": "a", "raw": "fn"}])
    assert (client.calls, waits) == (1, [])


def test_a_rate_limit_is_tried_again(monkeypatch):
    form, client, waits = _failing_form(monkeypatch, [_status_error(429), _status_error(429)])

    assert form.clean_labels([{"id": "a", "raw": "fn"}]) == {"a": "Etunimi"}
    assert (client.calls, waits) == (3, [1, 2])
