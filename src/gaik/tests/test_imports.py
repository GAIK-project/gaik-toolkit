"""Basic import tests to ensure package structure is correct."""


def test_gaik_import():
    """Test that gaik package can be imported."""
    import gaik

    assert hasattr(gaik, "__version__")


def test_extractor_import():
    """Test that extractor module can be imported."""
    from gaik.building_blocks import extractor

    assert extractor is not None


def test_parsers_import():
    """Test that parsers module can be imported."""
    from gaik.building_blocks import parsers

    assert parsers is not None


def test_transcriber_import():
    """Test that transcriber module can be imported."""
    from gaik.building_blocks import transcriber

    assert transcriber is not None


def test_doc_classifier_import():
    """Test that doc_classifier module can be imported."""
    from gaik.building_blocks import doc_classifier

    assert doc_classifier is not None
