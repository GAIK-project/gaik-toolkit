"""
Audio-to-structured-data pipeline: transcribe audio and extract structured fields.
"""

from .pipeline import AudioToStructuredData, PipelineResult

__all__ = ["AudioToStructuredData", "PipelineResult"]
