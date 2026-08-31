"""Building blocks namespace for gaik components.

Names only -- submodules are not imported here, so a missing optional
dependency never breaks ``import gaik.software_components``.
"""

__all__ = [
    "config",
    "llm",
    "extractor",
    "vision_extractor",
    "transcriber",
    "enhance_transcript",
    "text_to_speech",
    "parallel_transcriber",
    "parsers",
    "doc_classifier",
    "form_understander",
    "RAG",
    "postgres_agent",
    "tabular_agent",
    "evaluators",
    "validators",
]
