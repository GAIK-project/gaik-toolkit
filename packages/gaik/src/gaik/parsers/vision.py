"""Vision-enabled PDF to Markdown parsing utilities.

This module exposes :class:`VisionParser`, a helper that converts PDF pages to images
and sends them to OpenAI's vision-enabled chat completions (including Azure
OpenAI deployments).

Example
-------
>>> from gaik.parsers.vision import VisionParser, get_openai_config
>>> parser = VisionParser(get_openai_config(use_azure=True))
>>> markdown_pages = parser.convert_pdf("invoice.pdf")
"""

from __future__ import annotations

import base64
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass

try:  # Optional dependency, documented via extra: gaik[vision]
    from dotenv import load_dotenv as _load_dotenv  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    _load_dotenv = None

try:
    from openai import AzureOpenAI, OpenAI
except ImportError as exc:  # pragma: no cover - optional dependency guard
    raise ImportError(
        "VisionParser requires the 'openai' package. Install extras with 'pip install gaik[parser]'"
    ) from exc

try:
    import fitz  # PyMuPDF
except ImportError as exc:  # pragma: no cover - optional dependency guard
    raise ImportError(
        "VisionParser requires the 'PyMuPDF' package. Install extras with "
        "'pip install gaik[parser]'"
    ) from exc

__all__ = ["OpenAIConfig", "VisionParser", "get_openai_config"]

logger = logging.getLogger(__name__)


def _load_env() -> None:
    """Load environment variables from ``.env`` if python-dotenv is available."""

    if _load_dotenv is not None:
        _load_dotenv()


def _first_env(*keys: str) -> str | None:
    """Return the first environment variable value that is set."""

    for key in keys:
        value = os.getenv(key)
        if value:
            return value
    return None


@dataclass
class OpenAIConfig:
    """Configuration for OpenAI or Azure OpenAI vision requests."""

    model: str
    use_azure: bool = True
    api_key: str | None = None
    azure_endpoint: str | None = None
    azure_audio_endpoint: str | None = None
    api_version: str | None = None

    def azure_base_endpoint(self) -> str | None:
        """Return the sanitized Azure endpoint without deployment path."""

        if not self.azure_endpoint:
            return None

        endpoint = self.azure_endpoint
        # Azure SDK expects the base endpoint, not deployment-specific.
        if "/openai/deployments/" in endpoint:
            endpoint = endpoint.split("/openai/deployments/")[0]
        return endpoint.rstrip("?&")


def get_openai_config(use_azure: bool = True) -> OpenAIConfig:
    """Build a default :class:`OpenAIConfig` from environment variables.

    Parameters
    ----------
    use_azure:
        Prefer Azure OpenAI environment variables when ``True``. When ``False``,
        fall back to standard OpenAI API credentials.
    """

    _load_env()

    if use_azure:
        api_key = _first_env("AZURE_API_KEY", "AZURE_OPENAI_API_KEY")
        endpoint = _first_env("AZURE_ENDPOINT", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_BASE")
        api_version = _first_env(
            "AZURE_API_VERSION",
            "AZURE_OPENAI_API_VERSION",
            "2024-12-01-preview",
        )
        model = _first_env(
            "AZURE_DEPLOYMENT", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_MODEL", "gpt-4.1"
        )
        return OpenAIConfig(
            use_azure=True,
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
            model=model or "gpt-4.1",
        )

    api_key = _first_env("OPENAI_API_KEY")
    model = _first_env("OPENAI_MODEL", "gpt-4o-2024-11-20") or "gpt-4o-2024-11-20"
    return OpenAIConfig(
        use_azure=False,
        api_key=api_key,
        model=model,
    )


class VisionParser:
    """Convert PDFs to Markdown using OpenAI vision models."""

    def __init__(
        self,
        openai_config: OpenAIConfig,
        *,
        custom_prompt: str | None = None,
        use_context: bool = True,
        max_tokens: int = 16_000,
        temperature: float = 0.0,
    ) -> None:
        self.config = openai_config
        self.custom_prompt = custom_prompt or self._default_prompt()
        self.use_context = use_context
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = self._initialize_client()

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def convert_pdf(self, pdf_path: str, *, dpi: int = 200, clean_output: bool = True) -> list[str]:
        """Convert a PDF into Markdown pages.

        Parameters
        ----------
        pdf_path:
            Absolute or relative path to the PDF.
        dpi:
            Rendering resolution for the PDF to image conversion (default ``200``).
        clean_output:
            When ``True`` merge and clean multi-page output via a post-processing
            LLM call.
        """

        images = self._pdf_to_images(pdf_path, dpi=dpi)
        markdown_pages: list[str] = []

        for index, image in enumerate(images, start=1):
            context = markdown_pages[-1] if (markdown_pages and self.use_context) else None
            markdown = self._parse_image(image, page=index, previous_context=context)
            markdown_pages.append(markdown)

        if clean_output and len(markdown_pages) > 1:
            return [self._clean_markdown(markdown_pages)]
        return markdown_pages

    def save_markdown(
        self,
        markdown_pages: Sequence[str],
        output_path: str,
        *,
        separator: str = "\n\n---\n\n",
    ) -> None:
        """Persist Markdown pages to disk."""

        if len(markdown_pages) == 1:
            payload = markdown_pages[0]
        else:
            payload = separator.join(markdown_pages)

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(payload)
        logger.info("Markdown saved to %s", output_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _initialize_client(self) -> AzureOpenAI | OpenAI:
        config = self.config

        if not config.api_key:
            raise ValueError(
                "OpenAI API key is required. Provide it in OpenAIConfig or via env vars."
            )

        if config.use_azure:
            endpoint = config.azure_base_endpoint()
            if not endpoint:
                raise ValueError(
                    "Azure endpoint is required when use_azure=True. Set 'azure_endpoint' "
                    "in OpenAIConfig"
                )

            if not config.api_version:
                raise ValueError("Azure API version is required when use_azure=True.")

            logger.debug("Initializing Azure OpenAI client for endpoint %s", endpoint)
            return AzureOpenAI(
                api_key=config.api_key,
                api_version=config.api_version,
                azure_endpoint=endpoint,
            )

        logger.debug("Initializing standard OpenAI client")
        return OpenAI(api_key=config.api_key)

    def _pdf_to_images(self, pdf_path: str, *, dpi: int) -> list[bytes]:
        """Convert PDF pages to PNG image bytes using PyMuPDF.

        Returns a list of PNG image data as bytes objects.
        """
        logger.info("Converting PDF %s to images at %s DPI", pdf_path, dpi)
        images: list[bytes] = []
        doc = fitz.open(pdf_path)

        # Calculate zoom factor from DPI (72 is the default DPI in PDFs)
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        for page_num in range(len(doc)):
            # Render page to pixmap with specified DPI
            pix = doc[page_num].get_pixmap(matrix=mat)
            # Get PNG bytes directly
            png_bytes = pix.tobytes("png")
            images.append(png_bytes)

        doc.close()
        logger.debug("Converted %s pages", len(images))
        return images

    def _image_to_base64(self, image_bytes: bytes) -> str:
        """Convert PNG image bytes to base64 string."""
        return base64.b64encode(image_bytes).decode("utf-8")

    def _parse_image(
        self,
        image_bytes: bytes,
        *,
        page: int,
        previous_context: str | None,
    ) -> str:
        logger.info("Parsing page %s", page)

        payload = [
            {
                "type": "text",
                "text": self._build_prompt(previous_context),
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{self._image_to_base64(image_bytes)}"},
            },
        ]

        response = self._client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": payload}],
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        content = response.choices[0].message.content
        if content is None:
            raise RuntimeError("Vision model returned empty content")
        return content

    def _clean_markdown(self, markdown_pages: Sequence[str]) -> str:
        logger.info("Cleaning and merging markdown output")

        combined = "\n\n---PAGE_BREAK---\n\n".join(markdown_pages)
        cleanup_prompt = self._cleanup_prompt().format(markdown=combined)

        response = self._client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": cleanup_prompt}],
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Cleanup LLM returned empty output")

        trimmed = content.strip()
        if trimmed.startswith("```"):
            trimmed = trimmed.strip("`").strip()
        return trimmed

    def _build_prompt(self, previous_context: str | None) -> str:
        if not (previous_context and self.use_context):
            return self.custom_prompt

        tail = previous_context[-500:]
        return (
            f"{self.custom_prompt}\n\n"
            "CONTEXT FROM PREVIOUS PAGE:\n"
            "The previous page ended with the following content (last 500 characters):\n"
            "```\n"
            f"{tail}\n"
            "```\n\n"
            "If this page continues a table or section from the previous page, "
            "continue it seamlessly without repeating headers."
        )

    @staticmethod
    def _default_prompt() -> str:
        return (
            "Convert this document page to accurate markdown format. "
            "Follow these rules STRICTLY:\n\n"
            "**CRITICAL RULES:**\n"
            "1. **NO HALLUCINATION**: Only output content that is actually visible on the page\n"
            "2. **NO EMPTY ROWS**: Do NOT create empty table rows. If you see a table, "
            "only include rows with actual data\n"
            "3. **STOP when content ends**: When you reach the end of visible content, STOP. "
            "Do not continue with empty rows\n\n"
            "**Formatting Requirements:**\n"
            "- Tables: Use markdown table syntax with | separators\n"
            "- Multi-row cells: Keep item descriptions/notes in the same row as the item data\n"
            "- Table continuations: If a table continues from a previous page, continue it "
            "without repeating headers\n"
            "- Preserve ALL visible text: headers, data, footers, page numbers, everything\n"
            "- Keep numbers, dates, and text exactly as shown\n"
            "- Maintain document structure and layout\n\n"
            "**What to include:**\n"
            "- All table data\n"
            "- All text paragraphs\n"
            "- Company information, addresses\n"
            "- Terms and conditions\n"
            "- Page numbers, dates\n"
            "- Total amounts and summaries\n\n"
            "Return ONLY the markdown content, no explanations."
        )

    @staticmethod
    def _cleanup_prompt() -> str:
        return (
            "You are a document processing expert. Clean up and merge this multi-page markdown "
            "document.\n\n"
            "TASKS:\n"
            "1. **Remove artifacts**: Delete any empty table rows or hallucinated content "
            "(rows with only pipe separators and no data)\n"
            "2. **Merge broken tables**: When a table continues across pages (separated by "
            "---PAGE_BREAK---):\n"
            "   - Keep only ONE table header\n"
            "   - Merge all data rows into a single continuous table\n"
            "   - Remove page break markers within tables\n"
            "3. **Handle incomplete rows**: If a table row is split across pages, merge it into a "
            "complete row\n"
            "4. **Preserve all real content**: Keep all actual data, headers, footers, and text\n"
            "5. **Clean up formatting**: Ensure proper markdown syntax throughout\n"
            "6. **Do NOT hallucinate**: Only output what you see in the input\n\n"
            "INPUT MARKDOWN:\n"
            "```markdown\n"
            "{markdown}\n"
            "```\n\n"
            "OUTPUT: Return ONLY the cleaned, merged markdown. No explanations, no code block "
            "wrappers."
        )
