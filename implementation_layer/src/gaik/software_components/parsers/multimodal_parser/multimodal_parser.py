"""Multi-provider PDF-to-markdown parser with layout-aware extraction."""

from __future__ import annotations

import base64
import html
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import requests
from markdown_it import MarkdownIt

from .config import (
    create_claude_client,
    create_openai_client,
    get_claude_config,
    get_google_access_token,
    get_google_config,
    get_openai_config,
)
from .prompts import SYSTEM_PROMPTS, USER_PROMPTS

logger = logging.getLogger(__name__)

FENCED_BLOCK_RE = re.compile(
    r"^```[a-zA-Z0-9_-]*\s*\n(?P<body>.*?)(?:\n```\s*)?$", re.DOTALL
)
DIV_BLOCK_RE = re.compile(r"<div\b[^>]*>\s*(.*?)\s*</div>", re.DOTALL)
MARKDOWN_RENDERER = MarkdownIt("commonmark", {"html": True}).enable("table")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #f4f1ea;
      --paper: #fffdf8;
      --ink: #1f2328;
      --muted: #667085;
      --line: #c7bda8;
      --line-strong: #8f8166;
      --head: #efe6d4;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: linear-gradient(180deg, #ece6da 0%, var(--bg) 100%);
      color: var(--ink);
      font-family: "Georgia", "Times New Roman", serif;
      line-height: 1.5;
    }}
    main {{
      max-width: 1100px;
      margin: 32px auto;
      padding: 48px 56px;
      background: var(--paper);
      border: 1px solid #ddd2bd;
      box-shadow: 0 18px 50px rgba(69, 52, 26, 0.10);
    }}
    h1, h2, h3, h4, h5, h6 {{
      margin: 1.4em 0 0.6em;
      color: #2e2417;
      line-height: 1.2;
    }}
    h1 {{
      margin-top: 0;
      padding-bottom: 0.25em;
      border-bottom: 2px solid var(--line-strong);
      font-size: 2rem;
    }}
    p {{ margin: 0.8em 0; }}
    ul, ol {{ margin: 0.8em 0 0.8em 1.4em; }}
    li + li {{ margin-top: 0.2em; }}
    code {{
      padding: 0.12em 0.35em;
      background: #f2ede3;
      border: 1px solid #e2d7c4;
      border-radius: 4px;
      font-family: "Consolas", "Courier New", monospace;
      font-size: 0.95em;
    }}
    pre {{
      overflow-x: auto;
      padding: 14px 16px;
      background: #f5f0e6;
      border: 1px solid #ddd2bd;
      border-radius: 8px;
    }}
    pre code {{
      padding: 0;
      background: transparent;
      border: 0;
    }}
    table {{
      width: 100%;
      margin: 1.2em 0 1.8em;
      border-collapse: collapse;
      table-layout: fixed;
      background: white;
    }}
    th, td {{
      padding: 10px 12px;
      border: 1px solid var(--line);
      vertical-align: top;
      text-align: left;
      word-wrap: break-word;
    }}
    th {{
      background: var(--head);
      font-weight: 700;
    }}
    @media (max-width: 800px) {{
      main {{
        margin: 12px;
        padding: 24px 18px;
      }}
      th, td {{
        padding: 8px;
        font-size: 0.95rem;
      }}
    }}
  </style>
</head>
<body>
  <main>
{body}
  </main>
</body>
</html>
"""


@dataclass
class ParseResult:
    """Result of parsing a PDF document."""

    raw_markdown: str
    clean_markdown: str
    html: str | None


ModelProvider = Literal["openai", "claude", "google"]
ReasoningEffort = Literal["low", "medium", "high"]


class MultimodalParser:
    """Multi-provider PDF-to-markdown parser with layout-aware extraction."""

    def __init__(
        self,
        *,
        model_provider: ModelProvider = "openai",
        model: str | None = None,
        reasoning_effort: ReasoningEffort = "low",
        merge_table: bool = False,
        use_azure: bool = True,
        vertex_ai: bool = True,
        additional_instructions: str | None = None,
        create_html: bool = False,
    ):
        """
        Args:
            model_provider: Which LLM provider to use.
            model: Model name to use. If None, uses the default from config/env vars.
            reasoning_effort: Thinking/reasoning effort level.
            merge_table: If True, instructs the model to combine tables
                         split across multiple pages.
            use_azure: Whether to use Azure/Foundry (for openai and claude providers).
            vertex_ai: Whether to use Vertex AI (for google provider).
            additional_instructions: Extra text appended to the user prompt.
            create_html: If True, also produce an HTML version of the cleaned markdown.
        """
        if model_provider not in ("openai", "claude", "google"):
            raise ValueError(f"Unsupported model_provider: {model_provider}")
        if reasoning_effort not in ("low", "medium", "high"):
            raise ValueError(f"Unsupported reasoning_effort: {reasoning_effort}")

        self.model_provider = model_provider
        self.reasoning_effort = reasoning_effort
        self.merge_table = merge_table
        self.use_azure = use_azure
        self.vertex_ai = vertex_ai
        self.additional_instructions = additional_instructions
        self.create_html = create_html

        self.config = self._build_config()
        if model:
            self.config["model"] = model

    def _build_config(self) -> dict:
        """Build provider-specific config from the constructor flags."""
        if self.model_provider == "openai":
            return get_openai_config(use_azure=self.use_azure)
        elif self.model_provider == "claude":
            return get_claude_config(use_azure=self.use_azure)
        else:
            return get_google_config(vertex_ai=self.vertex_ai)

    def parse(self, pdf_path: str | Path) -> ParseResult:
        """Parse a PDF file and return structured output."""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        system_prompt = self._get_system_prompt()
        user_prompt = self._get_user_prompt()

        logger.info("Parsing %s with %s provider", pdf_path.name, self.model_provider)

        callers = {
            "openai": self._call_openai,
            "claude": self._call_claude,
            "google": self._call_google,
        }
        raw_output = callers[self.model_provider](pdf_path, system_prompt, user_prompt)
        raw_markdown = _unwrap_fenced_output(raw_output)

        if not raw_markdown.strip():
            raise ValueError("The model response did not contain any text output.")

        clean_md = _clean_markdown(raw_markdown)
        html_output = (
            _markdown_to_html(clean_md, title=pdf_path.stem) if self.create_html else None
        )

        return ParseResult(
            raw_markdown=raw_markdown,
            clean_markdown=clean_md,
            html=html_output,
        )

    # -- prompt helpers -------------------------------------------------------

    def _get_system_prompt(self) -> str:
        return SYSTEM_PROMPTS[self.model_provider]

    def _get_user_prompt(self) -> str:
        prompt = USER_PROMPTS[self.model_provider]

        merge_instruction = "If a table is split across multiple pages, combine it."
        if self.merge_table and merge_instruction not in prompt:
            prompt = prompt.rstrip() + "\n" + merge_instruction + "\n"

        if self.additional_instructions:
            prompt = prompt.rstrip() + "\n" + self.additional_instructions + "\n"

        return prompt

    # -- provider calls -------------------------------------------------------

    def _call_openai(self, pdf_path: Path, system_prompt: str, user_prompt: str) -> str:
        client = create_openai_client(self.config)
        response = client.responses.create(
            model=self.config["model"],
            instructions=system_prompt,
            input=[
                {
                    "role": "user",
                    "content": _build_openai_content(pdf_path, user_prompt),
                }
            ],
            reasoning={"effort": self.reasoning_effort},
            max_output_tokens=32768,
        )
        text = response.output_text.strip()
        if not text:
            raise ValueError("The OpenAI response did not contain any text output.")
        return text + "\n"

    def _call_claude(self, pdf_path: Path, system_prompt: str, user_prompt: str) -> str:
        client = create_claude_client(self.config)
        text_blocks: list[str] = []
        with client.messages.stream(
            model=self.config["model"],
            max_tokens=32768,
            system=system_prompt,
            thinking={"type": "adaptive"},
            output_config={"effort": self.reasoning_effort},
            messages=[
                {
                    "role": "user",
                    "content": _build_claude_content(pdf_path, user_prompt),
                },
            ],
        ) as stream:
            response = stream.get_final_message()
        text_blocks = [
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        ]
        if not text_blocks:
            raise ValueError("The Claude response did not contain any text blocks.")
        return "".join(text_blocks).strip() + "\n"

    def _call_google(self, pdf_path: Path, system_prompt: str, user_prompt: str) -> str:
        body = _build_google_body(pdf_path, system_prompt, user_prompt, self.reasoning_effort)

        if self.config.get("vertex_ai", True):
            token = get_google_access_token(self.config)
            url = self.config["generate_content_url"]
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            }
        else:
            api_key = self.config["api_key"]
            model = self.config["model"]
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/"
                f"models/{model}:generateContent?key={api_key}"
            )
            headers = {"Content-Type": "application/json; charset=utf-8"}

        response = requests.post(url, headers=headers, json=body, timeout=(30, 300))
        response.raise_for_status()

        payload = response.json()
        candidates = payload.get("candidates", [])
        if not candidates:
            raise ValueError(f"The Gemini response contained no candidates: {payload}")

        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [p.get("text", "") for p in parts if p.get("text")]
        if not text_parts:
            raise ValueError(f"The Gemini response contained no text parts: {payload}")

        return "".join(text_parts).strip() + "\n"


# -- content builders (module-level helpers) ----------------------------------


def _encode_pdf_base64(pdf_path: Path) -> str:
    return base64.b64encode(pdf_path.read_bytes()).decode("ascii")


def _build_openai_content(pdf_path: Path, user_prompt: str) -> list[dict]:
    data_url = f"data:application/pdf;base64,{_encode_pdf_base64(pdf_path)}"
    return [
        {"type": "input_file", "filename": pdf_path.name, "file_data": data_url},
        {"type": "input_text", "text": user_prompt},
    ]


def _build_claude_content(pdf_path: Path, user_prompt: str) -> list[dict]:
    return [
        {
            "type": "document",
            "title": pdf_path.name,
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": _encode_pdf_base64(pdf_path),
            },
        },
        {"type": "text", "text": user_prompt},
    ]


def _build_google_body(
    pdf_path: Path, system_prompt: str, user_prompt: str, reasoning_effort: str
) -> dict:
    return {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [
            {
                "role": "USER",
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": "application/pdf",
                            "data": _encode_pdf_base64(pdf_path),
                        }
                    },
                    {"text": user_prompt},
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 32768,
            "thinkingConfig": {"thinkingLevel": reasoning_effort},
        },
    }


# -- post-processing helpers --------------------------------------------------


def _unwrap_fenced_output(text: str) -> str:
    """Remove a model-added fenced code block wrapper."""
    stripped = text.strip()
    match = FENCED_BLOCK_RE.match(stripped)
    if match:
        return match.group("body").strip() + "\n"
    return stripped + "\n"


def _clean_markdown(text: str) -> str:
    """Strip outer layout div wrappers while keeping inner markdown and HTML."""
    unwrapped = _unwrap_fenced_output(text)
    blocks = DIV_BLOCK_RE.findall(unwrapped)
    if not blocks:
        return unwrapped.strip() + "\n"
    cleaned = [b.strip() for b in blocks if b.strip()]
    return "\n\n".join(cleaned).strip() + "\n"


def _markdown_to_html(markdown_text: str, title: str = "Parsed Document") -> str:
    """Render markdown to a styled standalone HTML document."""
    rendered = MARKDOWN_RENDERER.render(markdown_text)
    indented = "\n".join(f"    {line}" if line else "" for line in rendered.splitlines())
    return HTML_TEMPLATE.format(title=html.escape(title), body=indented)
