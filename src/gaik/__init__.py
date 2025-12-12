"""General AI Kit (GAIK) - AI/ML toolkit for Python.

AI toolkit with structured data extraction, document parsing, and audio/video transcription using OpenAI/Azure OpenAI.

Modules:
    - gaik.building_blocks.extractor: Schema generation and structured data extraction
    - gaik.building_blocks.parsers: Document parsing - PDFs and Word docs (vision models, PyMuPDF, python-docx, Docling)
    - gaik.building_blocks.transcriber: Audio/video transcription using Whisper with GPT enhancement
    - gaik.building_blocks.doc_classifier: Document classification into predefined categories

Example - Schema-based Extraction:
    >>> from gaik.building_blocks.extractor import SchemaGenerator, DataExtractor, get_openai_config
    >>> config = get_openai_config(use_azure=True)
    >>> generator = SchemaGenerator(config=config)
    >>> schema = generator.generate_schema("Extract name and age")
    >>> extractor = DataExtractor(config=config)
    >>> results = extractor.extract(
    ...     extraction_model=schema,
    ...     requirements=generator.item_requirements,
    ...     user_requirements="Extract name and age",
    ...     documents=["Alice is 25 years old"]
    ... )

Example - PDF Parsing:
    >>> from gaik.building_blocks.parsers import VisionParser, get_openai_config
    >>> config = get_openai_config(use_azure=True)
    >>> parser = VisionParser(openai_config=config)
    >>> pages = parser.convert_pdf("document.pdf")

Example - Audio Transcription:
    >>> from gaik.building_blocks.transcriber import Transcriber, get_openai_config
    >>> config = get_openai_config(use_azure=True)
    >>> transcriber = Transcriber(config)  # enhanced_transcript=True by default
    >>> result = transcriber.transcribe("meeting.mp3")
"""

import importlib.metadata

try:
    __version__ = importlib.metadata.version("gaik")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0.dev"

# Submodules are NOT imported automatically to avoid requiring optional dependencies.
# Users should import submodules explicitly:
#   from gaik.building_blocks.extractor import SchemaGenerator, DataExtractor
#   from gaik.building_blocks.parsers import VisionParser
#   from gaik.building_blocks.transcriber import Transcriber
#   from gaik.building_blocks.doc_classifier import DocumentClassifier

__all__ = [
    "__version__",
]

