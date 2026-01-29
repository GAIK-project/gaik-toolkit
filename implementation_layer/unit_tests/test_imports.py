"""Basic import tests to ensure package structure is correct."""


def test_gaik_import():
    """Test that gaik package can be imported."""
    import gaik

    assert hasattr(gaik, "__version__")


def test_extractor_import():
    """Test that extractor module can be imported."""
    from gaik.software_components import extractor

    assert extractor is not None


def test_parsers_import():
    """Test that parsers module can be imported."""
    from gaik.software_components import parsers

    assert parsers is not None


def test_transcriber_import():
    """Test that transcriber module can be imported."""
    from gaik.software_components import transcriber

    assert transcriber is not None


def test_doc_classifier_import():
    """Test that doc_classifier module can be imported."""
    from gaik.software_components import doc_classifier

    assert doc_classifier is not None


def test_embedder_import():
    """Test that embedder module can be imported."""
    from gaik.software_components.RAG import embedder

    assert embedder is not None


def test_vector_store_import():
    """Test that vector_store module can be imported."""
    from gaik.software_components.RAG import vector_store

    assert vector_store is not None


def test_retriever_import():
    """Test that retriever module can be imported."""
    from gaik.software_components.RAG import retriever

    assert retriever is not None


def test_answer_generator_import():
    """Test that answer_generator module can be imported."""
    from gaik.software_components.RAG import answer_generator

    assert answer_generator is not None
