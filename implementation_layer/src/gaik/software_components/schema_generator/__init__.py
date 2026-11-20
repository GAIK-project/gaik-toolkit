"""Public import alias for the extractor schema-generation API.

The implementation remains in :mod:`gaik.software_components.extractor` so
existing imports and persisted schemas keep working. This package provides a
clearer import path without creating a second software component.
"""

from gaik.software_components.extractor import (
    FieldChange,
    SchemaDiff,
    SchemaGenerationResult,
    SchemaGenerator,
    compare_requirements,
)

__all__ = [
    "SchemaGenerator",
    "SchemaGenerationResult",
    "SchemaDiff",
    "FieldChange",
    "compare_requirements",
]
