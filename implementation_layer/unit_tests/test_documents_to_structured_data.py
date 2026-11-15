"""Import tests for documents_to_structured_data pipeline."""


def test_pipeline_import():
    from gaik.software_modules.documents_to_structured_data import DocumentsToStructuredData

    pipeline = DocumentsToStructuredData(use_azure=False)
    assert pipeline is not None


def test_docx_and_docling_documents_reach_the_extractor_as_their_text():
    import pytest
    from gaik.software_modules.documents_to_structured_data import DocumentsToStructuredData

    class Parser:
        """Returns what DocxParser and DoclingParser return: the text with its metadata."""

        def parse_document(self, file_path):
            return {
                "file_path": file_path,
                "file_name": "invoice.docx",
                "text_content": "Invoice total 12.50\nDue 1 March",
                "word_count": 6,
            }

    pipeline = DocumentsToStructuredData(use_azure=False)

    for choice in ("docx", "docling"):
        assert pipeline._parse_document(choice, Parser(), "invoice.docx", {}) == [
            "Invoice total 12.50\nDue 1 March"
        ]
    with pytest.raises(ValueError, match="Unsupported parser_choice"):
        pipeline._parse_document("other", Parser(), "invoice.docx", {})
