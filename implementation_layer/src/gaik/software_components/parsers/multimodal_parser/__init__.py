"""Multimodal Parser

Multi-provider PDF-to-markdown parser that sends PDFs to OpenAI, Claude, or Google
Gemini for layout-aware extraction, producing raw markdown with layout metadata,
cleaned markdown, and optionally styled HTML.

Main Classes:
    - MultimodalParser: Parse PDFs using OpenAI, Claude, or Google Gemini

Configuration:
    - get_openai_config: Get OpenAI/Azure OpenAI configuration
    - create_openai_client: Create OpenAI client from config
    - get_claude_config: Get Anthropic Foundry configuration
    - create_claude_client: Create Anthropic Foundry client from config
    - get_google_config: Get Google Vertex AI configuration
    - get_google_access_token: Refresh and return a Google Cloud access token

Example:
    >>> from gaik.software_components.parsers.multimodal_parser import MultimodalParser
    >>> parser = MultimodalParser(model_provider="openai", use_azure=True, create_html=True)
    >>> result = parser.parse("document.pdf")
    >>> print(result.clean_markdown)
"""

from .config import (
    create_claude_client,
    create_openai_client,
    get_claude_config,
    get_google_access_token,
    get_google_config,
    get_openai_config,
)
from .multimodal_parser import MultimodalParser, ParseResult
from .pricing import compute_cost_usd, lookup_price
from .usage import UsageRecord

__all__ = [
    "MultimodalParser",
    "ParseResult",
    "UsageRecord",
    "compute_cost_usd",
    "lookup_price",
    "get_openai_config",
    "create_openai_client",
    "get_claude_config",
    "create_claude_client",
    "get_google_config",
    "get_google_access_token",
]

__version__ = "0.2.0"
