"""Image classification must preserve the chosen vision provider and endpoint."""

from types import SimpleNamespace

from gaik.software_components.doc_classifier.classifier import DocumentClassifier


def test_classifier_passes_complete_config_to_vision_parser(monkeypatch, tmp_path):
    from gaik.software_components.doc_classifier import classifier

    config = {
        "provider": "aitta",
        "model": "vision-model",
        "api_key": "test",
        "base_url": "https://aitta-api.csc.fi/openai/v1",
        "timeout": 600,
    }
    configs = []
    monkeypatch.setattr(classifier, "build_compat_client", lambda config: object())
    monkeypatch.setattr(
        classifier,
        "VisionParser",
        lambda openai_config: configs.append(openai_config)
        or SimpleNamespace(convert_image=lambda *args, **kwargs: "Document content"),
    )
    path = tmp_path / "document.png"
    path.write_bytes(b"synthetic-image")
    instance = DocumentClassifier(config)
    assert instance._extract_text(str(path), "vision") == "Document content"
    assert configs == [config]
