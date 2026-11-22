"""/form/understand returns each cleaned label with the page's own label.

Run from the repository root (the API is not in the library's test environment):

    uv run --no-project --python 3.12 --with-editable . \
        --with-requirements implementation_layer/api/requirements.txt --with pytest --with httpx \
        python -m pytest implementation_layer/api/tests -o addopts="" -q
"""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from gaik.software_components.form_understander import understander as gaik_understander
from gaik.software_components.form_understander.understander import LabelMapping

from implementation_layer.api.dependencies import verify_api_key
from implementation_layer.api.routers import form_understand


def _client(monkeypatch, answer: dict[str, str]):
    """A client for the route, with a model that answers ``answer`` (id -> label)."""
    calls = []

    def parse(**kwargs):
        calls.append(kwargs)
        entries = [{"id": key, "label": label} for key, label in answer.items()]
        mapping = LabelMapping.model_validate({"entries": entries})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=mapping))])

    raw = SimpleNamespace(
        beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
    )
    monkeypatch.setattr(gaik_understander, "build_compat_client", lambda config: raw)
    monkeypatch.setattr(
        form_understand, "get_form_config", lambda: {"use_azure": False, "model": "m"}
    )
    app = FastAPI()
    app.include_router(form_understand.router, prefix="/form/understand")
    app.dependency_overrides[verify_api_key] = lambda: "test"
    return TestClient(app), calls


def test_each_label_comes_with_the_page_label_and_whether_it_changed(monkeypatch):
    client, calls = _client(monkeypatch, {"a": "Etunimi", "b": "Sähköposti"})

    response = client.post(
        "/form/understand/",
        json={
            "fields": [
                {"id": "a", "label": "FieldInput:_ctl1:InputTextRow"},
                {"id": "b", "label": " Sähköposti: "},
                {"id": "c", "label": "Puhelin"},
            ],
            "languageHint": "fi",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["labels"] == [
        {
            "id": "a",
            "label": "Etunimi",
            "pageLabel": "FieldInput:_ctl1:InputTextRow",
            "changed": True,
            "truncated": False,
        },
        {
            "id": "b",
            "label": "Sähköposti",
            "pageLabel": "Sähköposti:",
            "changed": False,
            "truncated": False,
        },
        # no label from the model: the page's own label
        {
            "id": "c",
            "label": "Puhelin",
            "pageLabel": "Puhelin",
            "changed": False,
            "truncated": False,
        },
    ]
    # the id -> label mapping stays for existing clients
    assert body["mapping"] == {"a": "Etunimi", "b": "Sähköposti", "c": "Puhelin"}
    assert len(calls) == 1


def test_a_page_label_cut_to_60_characters_is_truncated_not_changed(monkeypatch):
    long_label = "Henkilön koko virallinen nimi sellaisena kuin se on väestörekisterissä"
    assert len(long_label) > 60
    # "a": the model gives back the page's own label, cut to 60 by the understander;
    # "b": the model gives no label, so the page's label is kept, cut to 60.
    client, _ = _client(monkeypatch, {"a": long_label})

    response = client.post(
        "/form/understand/",
        json={"fields": [{"id": "a", "label": long_label}, {"id": "b", "label": long_label}]},
    )

    assert response.status_code == 200
    cut = long_label[:60]
    assert response.json()["labels"] == [
        {"id": key, "label": cut, "pageLabel": long_label, "changed": False, "truncated": True}
        for key in ("a", "b")
    ]


def test_the_route_calls_describe_labels_with_the_fields(monkeypatch):
    seen = {}

    class _Understander:
        def __init__(self, config):
            pass

        def describe_labels(self, fields, language_hint=None):
            seen.update(fields=fields, language_hint=language_hint)
            return []

        def clean_labels(self, *args, **kwargs):
            raise AssertionError("the route gives the page label too")

    client, _ = _client(monkeypatch, {})
    monkeypatch.setattr(form_understand, "FormUnderstander", _Understander)

    response = client.post(
        "/form/understand/",
        json={
            "fields": [
                {
                    "id": "a",
                    "label": "Name",
                    "type": "text",
                    "htmlType": "input",
                    "parentHtmlSnippet": "<td>Name</td>",
                }
            ],
            "languageHint": "en",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"mapping": {}, "labels": []}
    assert seen == {
        "fields": [
            {
                "id": "a",
                "raw": "Name",
                "type": "text",
                "htmlType": "input",
                "parent": "<td>Name</td>",
            }
        ],
        "language_hint": "en",
    }


def test_repeated_field_ids_are_refused_before_the_model(monkeypatch):
    client, calls = _client(monkeypatch, {"a": "Name"})

    response = client.post(
        "/form/understand/",
        json={"fields": [{"id": "a", "label": "Etunimi"}, {"id": "a", "label": "Sukunimi"}]},
    )

    assert response.status_code == 422
    assert "repeated" in response.json()["detail"]
    assert calls == []


def test_an_empty_form_returns_empty_results_without_the_model(monkeypatch):
    client, calls = _client(monkeypatch, {"a": "Name"})

    response = client.post("/form/understand/", json={"fields": []})

    assert response.status_code == 200
    assert response.json() == {"mapping": {}, "labels": []}
    assert calls == []
