"""Vision-enabled PDF to Markdown parsing utilities.

This module exposes :class:`VisionParser`, a helper that converts PDF pages to images
and sends them to OpenAI's vision-enabled chat completions (including Azure
OpenAI deployments).

Example
-------
>>> from gaik.software_components.parsers.vision import VisionParser, get_openai_config
>>> parser = VisionParser(get_openai_config(use_azure=True))
>>> markdown_pages = parser.convert_pdf("invoice.pdf")
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gaik.software_components._log_names import file_tag
from gaik.software_components.endpoints import check_openai_endpoint
from gaik.software_components.env_file import load_env_file
from gaik.software_components.file_type import IMAGE_TYPES, MIME_TYPES, check_file_type
from gaik.software_components.input_limits import InputLimits
from gaik.software_components.llm.base import ProviderClient, UsageCounter
from gaik.software_components.llm.factory import create_llm_client
from gaik.software_components.llm.parameters import normalize_chat_kwargs
from gaik.software_components.llm.providers import Provider, resolve_provider
from gaik.software_components.source_material import (
    SOURCE_MATERIAL_INSTRUCTION,
    SourceMaterial,
    source_material_messages,
)

from ._cut_off import Reply, reply_cut_off

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

# A fence line: three or more backticks or tildes, with an optional language tag such
# as markdown or python (a backtick fence's tag holds no backtick).
_FENCE = re.compile(r"(?P<marks>`{3,}(?=[^`]*\Z)|~{3,})(?P<info>.*)\Z")
# Tags a model puts on a fence around the whole document.
_DOCUMENT_TAGS = frozenset({"markdown", "md"})


def _closes(fence: re.Match, opening: re.Match) -> bool:
    """A bare fence of the opening's character, at least as long, closes it."""
    marks, opened = fence["marks"], opening["marks"]
    return not fence["info"].strip() and marks[0] == opened[0] and len(marks) >= len(opened)


def _unwrap_fence(text: str) -> str:
    """The text without a code fence the model put around all of it.

    Fences are paired by nesting: one with a language tag opens a block, and a bare one
    closes the innermost open block when it has that block's character and at least
    its length; a shorter bare fence is text of the block. When the first fence closes
    on the last line, or the first fence is tagged markdown and the last line would
    close it, the pair wraps the whole text and is taken off. A first fence that closes
    earlier opens a code block of the document, which is kept; one that never closes is
    taken off.
    """
    lines = text.split("\n")
    fences = [_FENCE.match(line.strip()) for line in lines]
    if fences[0] is None:
        return text
    open_blocks, closed_at = [fences[0]], None
    for number, fence in enumerate(fences[1:], start=1):
        if fence is None:
            continue
        if _closes(fence, open_blocks[-1]):
            open_blocks.pop()
            if not open_blocks:
                closed_at = number
                break
        elif fence["info"].strip():
            open_blocks.append(fence)
    last = len(lines) - 1
    if closed_at is None:
        body = lines[1:]
    elif closed_at == last or (
        fences[0]["info"].strip().lower() in _DOCUMENT_TAGS
        and fences[last] is not None
        and _closes(fences[last], fences[0])
    ):
        body = lines[1:last]
    else:
        return text
    return "\n".join(body).strip()


# mimetypes maps .webp only from Python 3.13 on (or via the OS type table).
_IMAGE_MIME_TYPES = {".webp": "image/webp"}


def _load_env() -> None:
    """Load ``.env`` once, as the other configuration helpers do (``env_file``)."""

    load_env_file()


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
    base_url: str | None = None
    timeout: float | None = None
    max_retries: int | None = None
    http_client: Any = None
    # Hosts the application allows besides the provider's own (see the endpoints module).
    allowed_endpoint_hosts: str | Sequence[str] | None = None

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
        api_version = (
            _first_env(
                "AZURE_API_VERSION",
                "AZURE_OPENAI_API_VERSION",
            )
            or "2024-12-01-preview"
        )
        model = _first_env("AZURE_DEPLOYMENT", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_MODEL")
        return OpenAIConfig(
            use_azure=True,
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
            model=model or "gpt-4.1",
        )

    api_key = _first_env("OPENAI_API_KEY")
    model = _first_env("OPENAI_MODEL") or "gpt-4o-2024-11-20"
    return OpenAIConfig(
        use_azure=False,
        api_key=api_key,
        model=model,
        base_url=_first_env("OPENAI_BASE_URL"),
    )


class VisionParser:
    """Convert PDFs to Markdown using OpenAI vision models.

    Every PDF page becomes one model call, so a file over ``limits`` (size,
    pages, pixels of a rendered page or image) is refused with
    :class:`~gaik.software_components.input_limits.InputLimitError` before any
    page is rendered or sent.
    """

    def __init__(
        self,
        openai_config: OpenAIConfig | Mapping[str, Any],
        *,
        custom_prompt: str | None = None,
        use_context: bool = True,
        max_tokens: int = 16_000,
        temperature: float | None = 0.0,
        reasoning_effort: str | None = None,
        limits: InputLimits | None = None,
    ) -> None:
        self.limits = limits or InputLimits()
        self._request_config = dict(openai_config) if isinstance(openai_config, Mapping) else {}
        provider = (
            resolve_provider(config=self._request_config)
            if "provider" in self._request_config
            else None
        )
        self._use_shared_client = provider is not None and provider not in {
            Provider.OPENAI.value,
            Provider.AZURE.value,
            Provider.OPENAI_COMPATIBLE.value,
            Provider.AITTA.value,
        }
        self.config = self._coerce_config(openai_config)
        self._provider = provider
        self.custom_prompt = custom_prompt or self._default_prompt()
        self.use_context = use_context
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort
        self._client = self._initialize_client()
        self.usage = UsageCounter()
        """Token totals of every model call this parser made."""

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def convert_pdf(
        self,
        pdf_path: str,
        *,
        dpi: int = 200,
        clean_output: bool = True,
        first_pages: int | None = None,
    ) -> list[str]:
        """Convert a PDF into Markdown pages.

        Parameters
        ----------
        pdf_path:
            Absolute or relative path to the PDF.
        dpi:
            Rendering resolution for the PDF to image conversion (default ``200``).
        clean_output:
            When ``True`` merge and clean multi-page output via a post-processing
            LLM call. If that reply stops at ``max_tokens``, the per-page Markdown
            is returned instead, with a warning in the log, so no page is lost.
        first_pages:
            Convert only this many pages from the start, e.g. ``1`` to read the
            first page. The ``max_pages`` limit then applies to these pages, not
            to the whole document. ``None`` (default) converts every page.

        Raises
        ------
        InputLimitError
            If the PDF is over ``max_file_bytes`` or ``max_pages``, or a page
            rendered at ``dpi`` is over ``max_image_pixels``.
        FileTypeMismatchError
            If the content is another known type, or not the type the file's
            extension says (a ``ValueError``).
        """

        if first_pages is not None and first_pages < 1:
            raise ValueError("first_pages must be at least 1")
        self.limits.check_file_size(pdf_path)
        check_file_type(pdf_path, {"pdf"})
        images = self._pdf_to_images(pdf_path, dpi=dpi, first_pages=first_pages)
        markdown_pages: list[str] = []

        for index, image in enumerate(images, start=1):
            context = markdown_pages[-1] if (markdown_pages and self.use_context) else None
            markdown = self._parse_image(image, page=index, previous_context=context)
            markdown_pages.append(markdown)

        if clean_output and len(markdown_pages) > 1:
            merged = self._clean_markdown(markdown_pages)
            if merged is not None:
                return [merged]
        return markdown_pages

    def convert_image(self, image_path: str | Path) -> str:
        """Convert a single image file to Markdown.

        Unlike :meth:`convert_pdf` (which renders PDF pages to images first),
        this reads an existing image file (``.png``, ``.jpg``, ``.jpeg``,
        ``.webp``, ``.tiff`` …) and sends it straight to the vision model.

        Parameters
        ----------
        image_path:
            Path to the image file.

        Returns
        -------
        str
            Markdown extracted from the image.

        Raises
        ------
        InputLimitError
            If the file is over ``max_file_bytes`` or ``max_image_pixels``.
        FileTypeMismatchError
            If the content is not a PNG, JPEG, GIF, WebP, TIFF or BMP image, or
            not the type the file's extension says (a ``ValueError``).
        """

        image_path = Path(image_path)
        mime_type = (
            _IMAGE_MIME_TYPES.get(image_path.suffix.lower())
            or mimetypes.guess_type(image_path.name)[0]
        )
        if mime_type is not None and not mime_type.startswith("image/"):
            raise ValueError(f"Unsupported image type: {image_path.suffix}")
        # The content decides the type sent to the model, also for an unknown or
        # missing suffix (e.g. a temporary upload).
        self.limits.check_file_size(image_path)
        mime_type = MIME_TYPES[check_file_type(image_path, IMAGE_TYPES)]
        self.limits.check_image_file(image_path)
        image_bytes = image_path.read_bytes()
        return self._parse_image(image_bytes, page=1, previous_context=None, mime_type=mime_type)

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
        logger.info("Markdown saved to %s", file_tag(output_path))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _initialize_client(self) -> AzureOpenAI | OpenAI | ProviderClient:
        if self._use_shared_client:
            return create_llm_client(self._request_config)
        # Without a base_url the endpoint check and the SDK read OPENAI_BASE_URL (and
        # the Azure ones) from the environment, so a value kept in .env must be there.
        _load_env()
        config = self.config

        if not config.api_key:
            raise ValueError(
                "OpenAI API key is required. Provide it in OpenAIConfig or via env vars."
            )

        client_options: dict[str, Any] = {}
        if config.timeout is not None:
            client_options["timeout"] = config.timeout
        if config.max_retries is not None:
            client_options["max_retries"] = config.max_retries
        if config.http_client is not None:
            client_options["http_client"] = config.http_client

        if config.use_azure:
            endpoint = config.azure_base_endpoint()
            if not endpoint and not config.base_url:
                raise ValueError(
                    "Azure endpoint is required when use_azure=True. Set 'azure_endpoint' "
                    "in OpenAIConfig"
                )

            if not config.api_version:
                raise ValueError("Azure API version is required when use_azure=True.")
            check_openai_endpoint(
                {
                    "base_url": config.base_url,
                    "azure_endpoint": endpoint,
                    "allowed_endpoint_hosts": config.allowed_endpoint_hosts,
                },
                Provider.AZURE.value,
            )

            logger.debug(
                "Initializing Azure OpenAI client for endpoint %s", config.base_url or endpoint
            )
            if config.base_url:
                client_options["base_url"] = config.base_url
            else:
                client_options["azure_endpoint"] = endpoint
            return AzureOpenAI(
                api_key=config.api_key,
                api_version=config.api_version,
                **client_options,
            )

        logger.debug("Initializing standard OpenAI client")
        check_openai_endpoint(
            {"base_url": config.base_url, "allowed_endpoint_hosts": config.allowed_endpoint_hosts},
            self._provider
            if self._provider in {Provider.OPENAI_COMPATIBLE.value, Provider.AITTA.value}
            else Provider.OPENAI.value,
        )
        kwargs: dict[str, Any] = {"api_key": config.api_key, **client_options}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        return OpenAI(**kwargs)

    @staticmethod
    def _coerce_config(config: OpenAIConfig | Mapping[str, Any]) -> OpenAIConfig:
        """Normalize dict-based configs to OpenAIConfig."""

        if isinstance(config, OpenAIConfig):
            return config

        if not isinstance(config, Mapping):
            raise TypeError("openai_config must be an OpenAIConfig or a mapping.")

        provider = resolve_provider(config=dict(config)) if "provider" in config else None
        base_url = config.get("base_url")
        timeout = config.get("timeout")
        if provider == Provider.OPENAI_COMPATIBLE.value:
            for field in ("base_url", "model"):
                if not config.get(field):
                    raise ValueError(f"openai_compatible requires an explicit {field!r}")
        if provider == Provider.AITTA.value:
            base_url = base_url or "https://aitta-api.csc.fi/openai/v1"
            if timeout is None:
                timeout = 600.0

        return OpenAIConfig(
            model=config.get("model") or "gpt-4.1",
            use_azure=(
                provider == Provider.AZURE.value
                if provider is not None
                else config.get("use_azure", True)
            ),
            api_key=config.get("api_key"),
            azure_endpoint=config.get("azure_endpoint"),
            azure_audio_endpoint=config.get("azure_audio_endpoint"),
            api_version=config.get("api_version"),
            base_url=base_url,
            timeout=timeout,
            max_retries=config.get("max_retries"),
            http_client=config.get("http_client"),
            allowed_endpoint_hosts=config.get("allowed_endpoint_hosts"),
        )

    def _pdf_to_images(
        self, pdf_path: str, *, dpi: int, first_pages: int | None = None
    ) -> list[bytes]:
        """Convert PDF pages to PNG image bytes using PyMuPDF.

        Returns a list of PNG image data as bytes objects.
        """
        logger.info("Converting PDF %s to images at %s DPI", file_tag(pdf_path), dpi)
        images: list[bytes] = []
        name = Path(pdf_path).name

        # Calculate zoom factor from DPI (72 is the default DPI in PDFs)
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        with fitz.open(pdf_path) as doc:
            # PyMuPDF opens other formats too; ask what it opened.
            if not doc.is_pdf:
                raise ValueError(f"The content of '{name}' is not a PDF document.")
            page_count = doc.page_count
            if first_pages is not None:
                page_count = min(page_count, first_pages)
            self.limits.check_pages(page_count, name)
            # Check every page's image size before rendering any of them.
            for page_num in range(page_count):
                self.limits.check_rendered_page(
                    doc[page_num], zoom, f"{name}, page {page_num + 1} at {dpi} DPI"
                )
            for page_num in range(page_count):
                # Render page to pixmap with specified DPI
                pix = doc[page_num].get_pixmap(matrix=mat)
                # Get PNG bytes directly
                png_bytes = pix.tobytes("png")
                images.append(png_bytes)

        logger.debug("Converted %s pages", len(images))
        return images

    def _image_to_base64(self, image_bytes: bytes) -> str:
        """Convert PNG image bytes to base64 string."""
        return base64.b64encode(image_bytes).decode("utf-8")

    def _sampling_kwargs(self) -> dict[str, float | str]:
        """Return only sampling options explicitly configured by the caller."""
        kwargs: dict[str, float | str] = {}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self.reasoning_effort is not None:
            kwargs["reasoning_effort"] = self.reasoning_effort
        return kwargs

    def _parse_image(
        self,
        image_bytes: bytes,
        *,
        page: int,
        previous_context: str | None,
        mime_type: str = "image/png",
    ) -> str:
        logger.info("Parsing page %s", page)

        material = SourceMaterial()
        payload = [
            {
                "type": "text",
                "text": self._build_prompt(previous_context, material),
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{self._image_to_base64(image_bytes)}"
                },
            },
        ]

        # The page image and the previous page's text are material. The rule goes
        # in the user message: some served vision models refuse a system
        # message next to an image.
        payload[0]["text"] = f"{SOURCE_MATERIAL_INSTRUCTION}\n\n{payload[0]['text']}"
        content = self._chat_content([{"role": "user", "content": payload}])
        cut_off = getattr(content, "cut_off", False)
        if content is None or (cut_off and not content):
            # A reasoning model can spend the whole budget before it writes anything.
            raise RuntimeError(
                "Vision model returned empty content"
                + (f": the reply stopped at max_tokens={self.max_tokens}" if cut_off else "")
            )
        if cut_off:
            logger.warning("Page %s: the reply stopped at max_tokens=%s", page, self.max_tokens)
        return str(content)

    def _clean_markdown(self, markdown_pages: Sequence[str]) -> str | None:
        """The merged Markdown, or None when the reply stopped at ``max_tokens``."""
        logger.info("Cleaning and merging markdown output")

        combined = "\n\n---PAGE_BREAK---\n\n".join(markdown_pages)
        material = SourceMaterial()
        content = self._chat_content(
            source_material_messages(
                self._cleanup_prompt(), material.wrap(combined, label="markdown pages")
            )
        )
        if getattr(content, "cut_off", False):
            # A cut-off merge would replace every page with a document missing its end.
            logger.warning(
                "The cleanup reply stopped at max_tokens=%s; returning the %d pages unmerged",
                self.max_tokens,
                len(markdown_pages),
            )
            return None
        if not content:
            raise RuntimeError("Cleanup LLM returned empty output")

        return _unwrap_fence(material.strip_echo(content).strip())

    def _chat_content(self, messages: list[dict]) -> str | None:
        """The reply's text as a :class:`Reply`, which says whether it was cut off.

        None when the model returned no content and was not cut off.
        """
        if isinstance(self._client, ProviderClient):
            chat = self._client.chat(
                messages,
                model=self.config.model,
                max_tokens=self.max_tokens,
                **self._sampling_kwargs(),
            )
            self.usage.add(chat.usage)
            return Reply(chat.text or "", reply_cut_off(chat.raw))
        options = normalize_chat_kwargs(
            self.config.model,
            {"max_completion_tokens": self.max_tokens, **self._sampling_kwargs()},
            config=self._request_config,
        )
        response = self._client.chat.completions.create(
            model=self.config.model, messages=messages, **options
        )
        if response.usage:
            self.usage.add(
                {k: v for k, v in response.usage.model_dump().items() if isinstance(v, int)}
            )
        content = response.choices[0].message.content
        cut_off = reply_cut_off(response)
        return None if content is None and not cut_off else Reply(content or "", cut_off)

    def _build_prompt(self, previous_context: str | None, material: SourceMaterial) -> str:
        if not (previous_context and self.use_context):
            return self.custom_prompt

        tail = previous_context[-500:]
        return (
            f"{self.custom_prompt}\n\n"
            "CONTEXT FROM PREVIOUS PAGE:\n"
            "The previous page ended with the following content (last 500 characters):\n"
            f"{material.wrap(tail, label='end of previous page')}\n\n"
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
            "INPUT MARKDOWN: the source_material block in the user message.\n\n"
            "OUTPUT: Return ONLY the cleaned, merged markdown. No explanations, no code block "
            "wrappers."
        )
