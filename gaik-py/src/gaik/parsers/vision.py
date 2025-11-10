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
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from io import BytesIO

try:  # Optional dependency, documented via extra: gaik[vision]
    from dotenv import load_dotenv as _load_dotenv  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    _load_dotenv = None

try:
    from openai import AzureOpenAI, OpenAI
except ImportError as exc:  # pragma: no cover - optional dependency guard
    raise ImportError(
        "VisionParser requires the 'openai' package. Install extras with 'pip install gaik[vision]'"
    ) from exc

try:
    from pdf2image import convert_from_path
except ImportError as exc:  # pragma: no cover - optional dependency guard
    raise ImportError(
        "VisionParser requires the 'pdf2image' package. Install extras with "
        "'pip install gaik[vision]'"
    ) from exc

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - optional dependency guard
    raise ImportError(
        "VisionParser requires the 'Pillow' package. Install extras with 'pip install gaik[vision]'"
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
        poppler_path: str | None = None,
        use_context: bool = True,
        max_tokens: int = 16_000,
        temperature: float = 0.0,
    ) -> None:
        self.config = openai_config
        self.custom_prompt = custom_prompt or self._default_prompt()
        self.poppler_path = poppler_path
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

    def _pdf_to_images(self, pdf_path: str, *, dpi: int) -> Iterable[Image.Image]:
        logger.info("Converting PDF %s to images at %s DPI", pdf_path, dpi)
        images = convert_from_path(pdf_path, dpi=dpi, poppler_path=self.poppler_path)
        logger.debug("Converted %s pages", len(images))
        return images

    def _image_to_base64(self, image: Image.Image) -> str:
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _parse_image(
        self,
        image: Image.Image,
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
                "image_url": {"url": f"data:image/png;base64,{self._image_to_base64(image)}"},
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
            "Please convert this document page to markdown format with the following "
            "requirements:\n\n"
            "1. Preserve ALL content exactly as it appears\n"
            "2. Maintain the document structure and hierarchy\n"
            "3. For tables:\n"
            "   - Use proper markdown table syntax with | separators\n"
            "   - If this page continues a table from the previous page, continue the table "
            "seamlessly\n"
            "   - Do NOT repeat table headers unless they appear on this page\n"
            "   - Preserve multi-row cells by repeating content or using appropriate formatting\n"
            "   - Maintain column alignment\n"
            "   - Keep all headers and data intact\n"
            "   - For item descriptions or notes within table cells, keep them in the same row\n"
            "4. Preserve formatting like bold, italic, lists, etc.\n"
            "5. For images or charts, describe them briefly in [Image: description] format\n"
            "6. Maintain the reading order and layout flow\n"
            "7. Keep numbers, dates, and special characters exactly as shown\n\n"
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
