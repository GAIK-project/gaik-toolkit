"""Text embedding building block."""

from gaik.software_components.config import create_openai_client, get_openai_config

from .embedder import Embedder, embed_texts

__all__ = [
    "Embedder",
    "embed_texts",
    "get_openai_config",
    "create_openai_client",
]

__version__ = "0.1.0"
