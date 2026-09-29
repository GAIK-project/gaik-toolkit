"""JevClassifier: label choice, confidence gate, hierarchy, batches and files."""

from types import SimpleNamespace

import pytest

pytest.importorskip("typesafe_sdk")

from gaik.software_components.jev_classifier import JevClassifier  # noqa: E402


class FakeClient:
    """Stands in for typesafe_sdk.TypeSafeClient and records what it was asked."""

    def __init__(self, choice="invoice", confidence=0.97, fail_on=None):
        self.choice = choice
        self.confidence = confidence
        self.fail_on = fail_on
        self.calls = []

    def system_one(self, state, questions):
        self.calls.append((state, questions))
        if self.fail_on and self.fail_on in state:
            raise RuntimeError("upstream 502")
        answer = SimpleNamespace(
            choice=self.choice,
            confidence=self.confidence,
            probabilities={self.choice: self.confidence, "other": 1 - self.confidence},
        )
        return SimpleNamespace(choices={"label": answer}, model="jev-1.13.0")


def make(**kwargs):
    fake = FakeClient(**kwargs)
    return JevClassifier(api_key="", client=fake), fake


def test_returns_label_probabilities_and_model():
    classifier, fake = make()
    result = classifier.classify("Invoice 4412, due in 30 days", ["invoice", "receipt"])
    assert result["class"] == "invoice"
    assert result["predicted"] == "invoice"
    assert result["confidence"] == 0.97
    assert result["probabilities"]["invoice"] == 0.97
    assert result["model"] == "jev-1.13.0"
    assert len(fake.calls) == 1


def test_descriptions_reach_jev_as_choice_criteria():
    classifier, fake = make()
    classifier.classify(
        "text", {"invoice": "asks for payment", "receipt": None}, instructions="Which document?"
    )
    question = fake.calls[0][1]["label"]
    assert question.criteria == {"invoice": "asks for payment", "receipt": None}
    assert question.instructions == "Which document?"


def test_low_confidence_becomes_unknown():
    classifier, _ = make(confidence=0.6)
    result = classifier.classify("text", ["invoice", "receipt"], min_confidence=0.9)
    assert result["class"] == "unknown"
    assert result["predicted"] == "invoice"


def test_confident_answer_passes_the_gate():
    classifier, _ = make(confidence=0.95)
    result = classifier.classify("text", ["invoice", "receipt"], min_confidence=0.9)
    assert result["class"] == "invoice"


def test_low_confidence_reports_the_broader_label_from_the_hierarchy():
    classifier, fake = make(choice="invoice", confidence=0.5)
    result = classifier.classify(
        "text",
        ["invoice", "receipt"],
        min_confidence=0.9,
        hierarchy={"invoice": "financial document", "receipt": "financial document"},
    )
    assert result["class"] == "financial document"
    assert result["predicted"] == "invoice"
    assert len(fake.calls) == 1  # no second request


def test_hierarchy_must_name_known_labels():
    classifier, _ = make()
    with pytest.raises(ValueError, match="hierarchy"):
        classifier.classify("text", ["a", "b"], hierarchy={"c": "d"})


@pytest.mark.parametrize("classes", [["only-one"], ["a", "a"], {"a": None}, ["a", " "]], ids=str)
def test_rejects_invalid_classes(classes):
    classifier, _ = make()
    with pytest.raises(ValueError):
        classifier.classify("text", classes)


def test_rejects_empty_text_and_bad_thresholds():
    classifier, _ = make()
    with pytest.raises(ValueError):
        classifier.classify("   ", ["a", "b"])
    with pytest.raises(ValueError):
        classifier.classify("text", ["a", "b"], min_confidence=1.5)
    with pytest.raises(ValueError):
        classifier.classify("text", ["a", "b"], max_chars=50_001)


def test_input_is_cut_to_max_chars():
    classifier, fake = make()
    classifier.classify("x" * 500, ["a", "b"], max_chars=100)
    assert len(fake.calls[0][0]) == 100


def test_api_key_is_required_without_a_client():
    with pytest.raises(ValueError, match="api_key"):
        JevClassifier(api_key="  ")


def test_builds_a_sdk_client_from_key_and_base_url():
    classifier = JevClassifier(api_key="gd_test", base_url="https://gaik-decide.example.test")
    assert type(classifier.client).__name__ == "TypeSafeClient"
    assert classifier.model == "jev-1.13.0"


def test_classify_many_keeps_order_and_isolates_failures():
    classifier, _ = make(fail_on="boom")
    results = classifier.classify_many(["one", "boom", "three"], ["invoice", "receipt"])
    assert [r["class"] for r in results] == ["invoice", "unknown", "invoice"]
    assert "upstream 502" in results[1]["error"]
    assert "error" not in results[0]


def test_classify_many_fails_fast_on_bad_classes():
    classifier, fake = make()
    with pytest.raises(ValueError):
        classifier.classify_many(["one", "two"], ["only-one"])
    assert fake.calls == []


def test_classify_file_reads_docx_text(tmp_path):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("Invoice 4412. Amount due 1 240 EUR.")
    path = tmp_path / "bill.docx"
    document.save(path)
    classifier, fake = make()
    results = classifier.classify_file(str(path), ["invoice", "receipt"])
    assert results["bill.docx"]["class"] == "invoice"
    assert "Invoice 4412" in fake.calls[0][0]


def test_classify_file_directory_isolates_a_bad_file(tmp_path):
    (tmp_path / "broken.pdf").write_bytes(b"not a pdf")
    (tmp_path / "notes.txt").write_text("ignored")
    classifier, _ = make()
    results = classifier.classify_file(str(tmp_path), ["invoice", "receipt"])
    assert list(results) == ["broken.pdf"]
    assert results["broken.pdf"]["class"] == "unknown"
    assert results["broken.pdf"]["error"]


def test_classify_file_rejects_unsupported_and_missing(tmp_path):
    classifier, _ = make()
    image = tmp_path / "scan.png"
    image.write_bytes(b"x")
    with pytest.raises(ValueError, match="Unsupported"):
        classifier.classify_file(str(image), ["a", "b"])
    with pytest.raises(FileNotFoundError):
        classifier.classify_file(str(tmp_path / "missing.pdf"), ["a", "b"])
    with pytest.raises(ValueError, match="No supported files"):
        classifier.classify_file(str(tmp_path), ["a", "b"])
