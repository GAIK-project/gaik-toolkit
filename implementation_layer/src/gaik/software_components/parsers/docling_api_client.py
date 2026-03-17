"""HTTP client parser for Docling service endpoints.

This parser sends documents to a remote parsing service and returns parsed markdown
and metadata without saving output locally.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests


class DoclingApiClientParser:
    """Client for remote document parsing service."""

    def __init__(
        self,
        *,
        api_base: str,
        password: str,
        timeout_seconds: int = 60 * 30,
        healthcheck_timeout_seconds: int = 30,
    ) -> None:
        if not api_base:
            raise ValueError("api_base is required")
        if not password:
            raise ValueError("password is required")

        self.api_base = api_base.rstrip("/")
        self.password = password
        self.timeout_seconds = timeout_seconds
        self.healthcheck_timeout_seconds = healthcheck_timeout_seconds

    def parse_document(self, document_path: str | Path) -> dict[str, Any]:
        """Parse a document through remote service and return markdown+metadata."""
        start_time = time.perf_counter()

        input_file = Path(document_path)
        if not input_file.exists():
            raise FileNotFoundError(f"Document file not found: {input_file}")

        print(f"Sending document: {input_file.name} ...")

        # Health check
        r = requests.get(f"{self.api_base}/health", timeout=self.healthcheck_timeout_seconds)
        r.raise_for_status()
        print(f"Server OK - {r.json()}")

        with input_file.open("rb") as f:
            files = {"file": (input_file.name, f)}
            print("Parsing... (this may take a while)")
            r = requests.post(
                f"{self.api_base}/parsedocument",
                files=files,
                headers={"key": self.password},
                timeout=self.timeout_seconds,
            )
            if r.status_code >= 400:
                print(f"Server returned HTTP {r.status_code}")
                try:
                    print("Error response:", r.json())
                except Exception:
                    print("Error response:", r.text)
                r.raise_for_status()

        payload = r.json()
        parsed_markdown = (payload.get("parsed_markdown") or "").strip()
        metadata = payload.get("metadata") or {}
        source_file = payload.get("source_file") or input_file.name

        return {
            "source_file": source_file,
            "parsed_markdown": parsed_markdown,
            "metadata": metadata,
            "elapsed_seconds": round(time.perf_counter() - start_time, 3),
        }


def parse_document_via_api(
    document_path: str | Path,
    *,
    api_base: str,
    password: str,
    timeout_seconds: int = 60 * 30,
    healthcheck_timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Convenience wrapper for one-off API parsing calls."""
    parser = DoclingApiClientParser(
        api_base=api_base,
        password=password,
        timeout_seconds=timeout_seconds,
        healthcheck_timeout_seconds=healthcheck_timeout_seconds,
    )
    return parser.parse_document(document_path)
