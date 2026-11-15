"""Source Tracing

Evidence for extracted values. The model is asked for one verbatim quote per value; plain
code then finds each quote in the source, compares the value with it, and reports whether a
person can trust the value on its evidence. For PDFs it also gives the quote's position on
the page. No model is used for the check, and no extractor is changed: the class works
around the extractor you call.

Main Classes:
    - SourceTracing: ``augment`` a task to ask for quotes, then ``check_text`` / ``check_pdf``
    - TraceReport: the result of a check (``summary()``, ``to_dict()``, ``items``)
    - TracedValue: one value with its quote, status, verdict and position
    - TracePolicy: the judgment calls of the check

Example:
    >>> from gaik.software_components.source_tracing import SourceTracing
    >>> st = SourceTracing()
    >>> task = st.augment(Invoice, "Extract the invoice", source="text")
    >>> results = extractor.extract(
    ...     extraction_model=task.model, requirements=reqs,
    ...     user_requirements=task.prompt, documents=[text],
    ... )
    >>> clean, report = st.check_text(results, [text])
    >>> report.summary()
"""

from .augment import (
    SOURCE_INSTRUCTION,
    SOURCES_FIELD,
    TEXT_SOURCE_INSTRUCTION,
    Augmented,
    Source,
    SourceList,
    with_sources,
)
from .models import TracedValue, TracePolicy, TraceReport
from .source_tracing import SourceTracing, transcript_used

__all__ = [
    "SourceTracing",
    "TraceReport",
    "TracedValue",
    "TracePolicy",
    "Augmented",
    "Source",
    "SourceList",
    "with_sources",
    "transcript_used",
    "SOURCES_FIELD",
    "SOURCE_INSTRUCTION",
    "TEXT_SOURCE_INSTRUCTION",
]

__version__ = "0.1.0"
