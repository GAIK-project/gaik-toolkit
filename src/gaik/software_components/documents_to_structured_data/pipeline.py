"""
Reusable pipeline to parse documents (PDF/images/DOCX) and extract structured data.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import io
import json
from pathlib import Path
from typing import Any, Sequence
from contextlib import redirect_stdout

from gaik.building_blocks.config import get_openai_config
from gaik.building_blocks.extractor import DataExtractor, SchemaGenerator, ExtractionRequirements
from gaik.building_blocks.extractor.schema import print_pydantic_schema

# Optional parsers
try:
    from gaik.building_blocks.parsers import VisionParser, DoclingParser, PyMuPDFParser, DocxParser
except ImportError:  # pragma: no cover - optional deps
    VisionParser = DoclingParser = PyMuPDFParser = DocxParser = None  # type: ignore


@dataclass
class PipelineResult:
    parsed_documents: list[str]
    extracted_fields: list[dict[str, Any]]
    schema: type
    requirements: ExtractionRequirements


class DocumentsToStructuredData:
    """End-to-end workflow: parse document(s) -> structured extraction."""

    def __init__(self, *, api_config: dict | None = None, use_azure: bool = True) -> None:
        self.api_config = api_config or get_openai_config(use_azure=use_azure)

    def run(
        self,
        *,
        file_path: str | Path,
        user_requirements: str,
        parser_choice: str = "vision_parser",
        parser_ctor: dict | None = None,
        parse_options: dict | None = None,
        extractor_ctor: dict | None = None,
        extract_options: dict | None = None,
        schema: type | None = None,
        requirements: ExtractionRequirements | None = None,
    ) -> PipelineResult:
        """
        Execute the pipeline: parse then extract structured data.

        Args:
            file_path: Document to parse (image/PDF/DOCX).
            user_requirements: Natural-language fields to extract.
            parser_choice: One of ["vision_parser", "docling", "pymupdf", "docx"].
            parser_ctor: Constructor kwargs for the chosen parser.
            parse_options: Call-time kwargs for the parser.
            extractor_ctor: Constructor kwargs for DataExtractor (e.g., model override).
            extract_options: Call-time kwargs for DataExtractor.extract().
            schema/requirements: Optional prebuilt schema and requirements to reuse.
        """
        parser_ctor = parser_ctor or {}
        parse_options = parse_options or {}

        parser = self._build_parser(parser_choice, parser_ctor)
        parsed_documents = self._parse_document(parser_choice, parser, file_path, parse_options)

        extractor_cfg = self.api_config.copy()
        model_override = (extractor_ctor or {}).get("model")
        if model_override:
            extractor_cfg["model"] = model_override

        if schema is None or requirements is None:
            schema_generator = SchemaGenerator(config=extractor_cfg)
            schema = schema_generator.generate_schema(user_requirements=user_requirements)
            requirements = schema_generator.item_requirements

        extractor_ctor = extractor_ctor or {}
        data_extractor = DataExtractor(config=extractor_cfg, **extractor_ctor)

        extract_opts = {
            "save_json": False,
            "json_path": "extraction_results.json",
        }
        if extract_options:
            extract_opts.update(extract_options)

        extracted_fields = data_extractor.extract(
            extraction_model=schema,
            requirements=requirements,
            user_requirements=user_requirements,
            documents=parsed_documents,
            **extract_opts,
        )

        return PipelineResult(
            parsed_documents=parsed_documents,
            extracted_fields=extracted_fields,
            schema=schema,
            requirements=requirements,
        )

    # ------------------------------------------------------------------
    # Parser helpers
    # ------------------------------------------------------------------
    def _build_parser(self, parser_choice: str, ctor: dict):
        choice = parser_choice.lower()
        if choice == "vision_parser":
            if VisionParser is None:
                raise ImportError("VisionParser not available. Install vision parser extras.")
            return VisionParser(openai_config=self.api_config, **ctor)
        if choice == "docling":
            if DoclingParser is None:
                raise ImportError("DoclingParser not available. Install docling extras.")
            return DoclingParser(**ctor)
        if choice == "pymupdf":
            if PyMuPDFParser is None:
                raise ImportError("PyMuPDFParser not available. Install pymupdf extras.")
            return PyMuPDFParser(**ctor)
        if choice == "docx":
            if DocxParser is None:
                raise ImportError("DocxParser not available. Install python-docx extras.")
            return DocxParser(**ctor)
        raise ValueError(f"Unsupported parser_choice: {parser_choice}")

    def _parse_document(self, parser_choice: str, parser, file_path: str | Path, parse_options: dict) -> list[str]:
        choice = parser_choice.lower()
        if choice == "vision_parser":
            pages = parser.convert_pdf(str(file_path), **parse_options)
            return pages if isinstance(pages, list) else [pages]
        if choice == "docling":
            parsed = parser.parse_document(str(file_path), **parse_options)
            return [str(parsed)]
        if choice == "pymupdf":
            text = parser.parse_pdf(str(file_path), **parse_options)
            return [text]
        if choice == "docx":
            text = parser.parse_document(str(file_path), **parse_options)
            return [text]
        raise ValueError(f"Unsupported parser_choice: {parser_choice}")

    # ------------------------------------------------------------------
    # Schema save/load helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_schema_dump(raw_dump: str) -> str:
        lines = raw_dump.splitlines()
        start_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("class "):
                start_idx = i
                break
        body = lines[start_idx:]
        while body and (set(body[-1].strip()) == {"="} or not body[-1].strip()):
            body.pop()
        return "\n".join(body).strip()

    def save_schema(
        self,
        schema: type,
        requirements: ExtractionRequirements,
        schema_dir: Path,
        schema_name: str,
    ) -> None:
        schema_dir.mkdir(parents=True, exist_ok=True)
        schema_path = schema_dir / f"{schema_name}.py"
        req_path = schema_dir / f"{schema_name}_requirements.json"

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            print_pydantic_schema(schema, title="Saved Schema")

        schema_code = self._clean_schema_dump(buffer.getvalue())
        template = f'''"""
Auto-generated schema module (do not edit manually).
"""

import decimal
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict

{schema_code}
'''
        schema_path.write_text(template, encoding="utf-8")

        payload = {
            "model_name": schema.__name__,
            "requirements": requirements.model_dump(),
        }
        req_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_schema(
        self, schema_dir: Path, schema_name: str
    ) -> tuple[type, ExtractionRequirements] | None:
        schema_path = schema_dir / f"{schema_name}.py"
        req_path = schema_dir / f"{schema_name}_requirements.json"
        if not (schema_path.exists() and req_path.exists()):
            return None

        data = json.loads(req_path.read_text(encoding="utf-8"))
        model_name = data["model_name"]
        requirements = ExtractionRequirements(**data["requirements"])

        spec = importlib.util.spec_from_file_location(model_name, schema_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)  # type: ignore[attr-defined]
        schema = getattr(module, model_name)
        return schema, requirements
