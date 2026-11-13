"""Operations

One function per common task around gaik's components, with shared settings: a timeout
that fits real documents, gaik's prints kept out of stdout, working files in a temporary
folder, and results as pydantic models. The components are not changed and not replaced;
each function calls them the way their own README shows.

Operations:
    - parse_document: the text of a PDF, DOCX or text file (no model call)
    - transcribe_audio: a recording as text
    - generate_fields: field definitions for a plain-language requirement
    - extract_fields: the fields filled from a text, each value with its quote
    - classify_text: one label for a text, with a probability per label

Helpers:
    - OperationSettings: provider, timeout, quiet stdout, working folder
    - build_schema: the extraction model for field definitions, without a model call
    - run_async: a blocking call in a worker thread, with an optional deadline
    - quiet_stdout: keep what the current thread or asyncio task prints out of stdout

Example:
    >>> from gaik.operations import FieldDefinition, extract_fields, parse_document
    >>> document = parse_document("service_note.pdf")
    >>> fields = [FieldDefinition(name="site"), FieldDefinition(name="visit_date", type="date")]
    >>> for item in extract_fields(document.text, fields):
    ...     print(item.label, item.value, item.evidence, item.verdict)

Importing this package loads the standard library and pydantic only. A component is
imported when the operation that needs it is first called.
"""

from ._runtime import quiet_stdout, run_async
from .audio import transcribe_audio
from .classify import classify_text
from .documents import parse_document
from .fields import ExtractionSchema, build_schema, extract_fields, generate_fields
from .models import Classification, ExtractedField, FieldDefinition, ParsedDocument, Transcript
from .settings import OperationSettings

__all__ = [
    "OperationSettings",
    "FieldDefinition",
    "ParsedDocument",
    "Transcript",
    "ExtractedField",
    "Classification",
    "ExtractionSchema",
    "parse_document",
    "transcribe_audio",
    "generate_fields",
    "extract_fields",
    "classify_text",
    "build_schema",
    "run_async",
    "quiet_stdout",
]

__version__ = "0.1.0"
