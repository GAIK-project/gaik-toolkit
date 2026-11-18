"""
Reusable pipeline to parse documents (PDF/images/DOCX) and extract structured data.
"""

from __future__ import annotations

import inspect
import io
import json
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gaik.software_components.config import get_openai_config
from gaik.software_components.extractor import (
    CompositeExtractionRequirements,
    DataExtractor,
    ExtractionRequirements,
    SchemaGenerator,
)
from gaik.software_components.extractor.saved_schema import (
    load_saved_model,
    save_model_file,
)
from gaik.software_components.extractor.schema import print_pydantic_schema
from gaik.software_modules._options import EXTRACT_SET_BY_MODULE, checked_options

# Optional parsers
try:
    from gaik.software_components.parsers import (
        DoclingParser,
        DocxParser,
        PyMuPDFParser,
        VisionParser,
    )
except ImportError:  # pragma: no cover - optional deps
    VisionParser = DoclingParser = PyMuPDFParser = DocxParser = None  # type: ignore


# The method each parser_choice reads the document with: the option check validates
# parse_options against it and _parse_document calls it, so the two cannot differ.
_PARSE_METHOD = {
    "vision_parser": "convert_pdf",
    "docling": "parse_document",
    "pymupdf": "parse_pdf",
    "docx": "parse_document",
}


@dataclass
class PipelineResult:
    parsed_documents: list[str]
    extracted_fields: list[dict[str, Any]]
    schema: type
    requirements: ExtractionRequirements | CompositeExtractionRequirements


def _schema_file_stem(schema_name: str) -> str:
    """Return ``schema_name`` if it is usable as a file name inside ``schema_dir``.

    The name becomes ``<schema_dir>/<name>.py``, so a name with a path separator
    or a parent reference would place the schema outside that directory.
    """
    name = str(schema_name)
    if not name or name in {".", ".."} or any(ch in name for ch in ("/", "\\", "\x00")):
        raise ValueError(
            f"Invalid schema_name {schema_name!r}: it must be a plain file name "
            "without path separators."
        )
    return name


def _text_of(parsed: Any) -> str:
    """The document's text from what ``parse_document`` returned.

    The Docling and DOCX parsers return a dict with the text under ``text_content``
    next to the file's path and metadata; the extractor reads the text only.
    """
    if isinstance(parsed, dict):
        return str(parsed.get("text_content") or "")
    return str(parsed)


class DocumentsToStructuredData:
    """End-to-end workflow: parse document(s) -> structured extraction."""

    def __init__(
        self,
        *,
        api_config: dict | None = None,
        use_azure: bool = True,
        parser_config: dict | None = None,
        extraction_config: dict | None = None,
    ) -> None:
        """Configure parsing and text extraction, optionally using different providers.

        ``parser_config`` must support the chosen parser's image input. Use
        ``extraction_config`` to select a separate text model for schema generation
        and extraction. Omitted stage configs retain the shared ``api_config``.
        """
        self.api_config = api_config
        if self.api_config is None and (parser_config is None or extraction_config is None):
            self.api_config = get_openai_config(use_azure=use_azure)
        self.parser_config = parser_config if parser_config is not None else self.api_config
        self.extraction_config = (
            extraction_config if extraction_config is not None else self.api_config
        )

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
        requirements: ExtractionRequirements | CompositeExtractionRequirements | None = None,
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

        Every option name must be a parameter of the component it goes to.
        Stage configs (``config``, ``api_config``, ``openai_config``) come from
        the constructor and are refused here; a :class:`ValueError` is raised
        before anything is parsed.
        """
        parser_class = self._parser_class(parser_choice)
        parser_ctor = checked_options(parser_ctor, parser_class, what="parser_ctor")
        parse_method = getattr(parser_class, _PARSE_METHOD[parser_choice.lower()], None)
        path_parameter = (
            next(
                (name for name in inspect.signature(parse_method).parameters if name != "self"),
                None,
            )
            if parse_method is not None
            else None
        )
        parse_options = checked_options(
            parse_options,
            parse_method,
            what="parse_options",
            set_by_module=(path_parameter,) if path_parameter else (),
        )
        extractor_ctor = checked_options(extractor_ctor, DataExtractor, what="extractor_ctor")
        extract_options = checked_options(
            extract_options,
            getattr(DataExtractor, "extract", None),
            what="extract_options",
            set_by_module=EXTRACT_SET_BY_MODULE,
        )

        parser = self._build_parser(parser_choice, parser_ctor)
        parsed_documents = self._parse_document(parser_choice, parser, file_path, parse_options)

        extractor_cfg = dict(self.extraction_config)
        model_override = extractor_ctor.get("model")
        if model_override:
            extractor_cfg["model"] = model_override

        if schema is None or requirements is None:
            schema_generator = SchemaGenerator(config=extractor_cfg)
            schema = schema_generator.generate_schema(user_requirements=user_requirements)
            requirements = schema_generator.item_requirements

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
    @staticmethod
    def _parser_class(parser_choice: str):
        choice = parser_choice.lower()
        if choice not in _PARSE_METHOD:
            raise ValueError(f"Unsupported parser_choice: {parser_choice}")
        parser_class = {
            "vision_parser": VisionParser,
            "docling": DoclingParser,
            "pymupdf": PyMuPDFParser,
            "docx": DocxParser,
        }[choice]
        if parser_class is None:
            raise ImportError(f"{choice} is not available. Install its parser extras.")
        return parser_class

    def _build_parser(self, parser_choice: str, ctor: dict):
        choice = parser_choice.lower()
        if choice == "vision_parser":
            if VisionParser is None:
                raise ImportError("VisionParser not available. Install vision parser extras.")
            return VisionParser(openai_config=self.parser_config, **ctor)
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

    def _parse_document(
        self, parser_choice: str, parser, file_path: str | Path, parse_options: dict
    ) -> list[str]:
        choice = parser_choice.lower()
        if choice not in _PARSE_METHOD:
            raise ValueError(f"Unsupported parser_choice: {parser_choice}")
        result = getattr(parser, _PARSE_METHOD[choice])(str(file_path), **parse_options)
        if choice == "vision_parser":
            return result if isinstance(result, list) else [result]
        if choice == "pymupdf":
            return [result]
        return [_text_of(result)]

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
        stem = _schema_file_stem(schema_name)
        schema_dir.mkdir(parents=True, exist_ok=True)
        schema_path = schema_dir / f"{stem}.py"
        req_path = schema_dir / f"{stem}_requirements.json"

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
        # The .py file is for people to read; load_schema reads the model file.
        schema_path.write_text(template, encoding="utf-8")
        # A model that cannot be saved as data removes an older model file, so
        # load_schema rebuilds from the requirements written below instead.
        save_model_file(schema, schema_dir / f"{stem}_model.json")

        payload = {
            "model_name": schema.__name__,
            "requirements": requirements.model_dump(),
        }
        req_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_schema(
        self, schema_dir: Path, schema_name: str
    ) -> tuple[type, ExtractionRequirements | CompositeExtractionRequirements] | None:
        stem = _schema_file_stem(schema_name)
        model_path = schema_dir / f"{stem}_model.json"
        req_path = schema_dir / f"{stem}_requirements.json"
        # A folder from an older gaik has <stem>.py but no model file; it is
        # rebuilt from the requirements where they determine the model.
        has_model = model_path.exists() or (schema_dir / f"{stem}.py").exists()
        if not (has_model and req_path.exists()):
            return None

        data = json.loads(req_path.read_text(encoding="utf-8"))
        model_name = data["model_name"]
        requirements_data = data["requirements"]
        is_composite = (
            data.get("requirements_type") == "parent_with_nested_list"
            or requirements_data.get("structure_type") == "parent_with_nested_list"
        )
        requirements_class = (
            CompositeExtractionRequirements if is_composite else ExtractionRequirements
        )
        requirements = requirements_class.model_validate(requirements_data)

        schema = load_saved_model(model_path, model_name, requirements)
        return schema, requirements
