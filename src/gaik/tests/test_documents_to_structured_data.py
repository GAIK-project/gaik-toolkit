"""Import tests for documents_to_structured_data pipeline."""

def test_pipeline_import():
    from gaik.software_components.documents_to_structured_data import DocumentsToStructuredData

    pipeline = DocumentsToStructuredData(use_azure=False)
    assert pipeline is not None
