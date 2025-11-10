"""Reusable vision-oriented parsers.

The submodule currently exposes :class:`VisionParser` for converting PDFs to
Markdown using OpenAI vision models.
"""

from .vision import OpenAIConfig, VisionParser, get_openai_config

__all__ = ["OpenAIConfig", "VisionParser", "get_openai_config"]
