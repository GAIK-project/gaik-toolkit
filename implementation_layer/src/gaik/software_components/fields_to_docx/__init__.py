"""Fields to Word

Write extracted fields to a Word file: a title, an optional line of facts, a table of labels
and values, an optional evidence column and an optional appendix with the source text or
transcript. python-docx only: no model call, no template file and no Pandoc.

Main Classes:
    - FieldsToDocx: ``write(fields, output_path, title=...)`` builds the file
    - DocxResult: the file as bytes, where it was written, and the row counts
    - FieldRow: one row of the table (label, value, evidence, verdict)

Functions:
    - to_rows: the rows ``write`` makes of a record or a sequence of rows

Example:
    >>> from gaik.software_components.fields_to_docx import FieldsToDocx
    >>> result = FieldsToDocx().write(
    ...     {"site": "Hall 3", "work_done": "Replaced the valve"},
    ...     "report.docx",
    ...     title="Service report",
    ... )
    >>> result.rows, result.filled
    (2, 2)
"""

from .fields_to_docx import DocxResult, FieldRow, FieldsToDocx, to_rows

__all__ = [
    "FieldsToDocx",
    "FieldRow",
    "DocxResult",
    "to_rows",
]

__version__ = "0.1.0"
