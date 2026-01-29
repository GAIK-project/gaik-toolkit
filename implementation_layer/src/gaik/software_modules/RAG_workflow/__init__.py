"""RAG workflow software component."""

from .pipeline import IndexResult, RAGWorkflow, RAGWorkflowResult

__all__ = [
    "RAGWorkflow",
    "RAGWorkflowResult",
    "IndexResult",
]

__version__ = "0.1.0"
