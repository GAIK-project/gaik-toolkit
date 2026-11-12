"""
Reusable software component to transcribe audio and extract structured data.
Built on Gaik's transcriber and extractor components
Takes any audio, transcribes, parses fields and dynamically builds schema, extracts required fields.
"""

from __future__ import annotations

import io
import json
from collections.abc import Sequence
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
    SavedSchemaError,
    load_saved_model,
    write_model_file,
)
from gaik.software_components.extractor.schema import print_pydantic_schema
from gaik.software_components.transcriber import Transcriber, TranscriptionResult


@dataclass
class PipelineResult:
    """Container for combined pipeline outputs."""

    transcription: TranscriptionResult  # Raw and enhanced transcript
    extracted_fields: list[dict[str, Any]]  # Structured data extracted
    schema: type  # The generated Pydantic schema
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


class AudioToStructuredData:
    """End-to-end workflow: audio -> transcript -> structured extraction."""

    def __init__(
        self,
        *,
        api_config: dict | None = None,
        use_azure: bool = True,
        transcription_config: dict | None = None,
        extraction_config: dict | None = None,
    ) -> None:
        """
        Initialize the pipeline.

        Args:
            api_config: OpenAI/Azure config. If None, built via get_openai_config(use_azure).
            use_azure: Whether to build default config for Azure (ignored if api_config supplied).
            transcription_config: Optional separate OpenAI/Azure audio configuration.
            extraction_config: Optional separate provider config for schema generation
                and text extraction, such as Google or Aitta.
        """
        self.api_config = api_config
        if self.api_config is None and (transcription_config is None or extraction_config is None):
            self.api_config = get_openai_config(use_azure=use_azure)
        self.transcription_config = (
            transcription_config if transcription_config is not None else self.api_config
        )
        self.extraction_config = (
            extraction_config if extraction_config is not None else self.api_config
        )

    def run(
        self,
        *,
        file_path: str | Path,
        user_requirements: str,
        transcriber_ctor: dict | None = None,
        transcribe_options: dict | None = None,
        extractor_ctor: dict | None = None,
        extract_options: dict | None = None,
        schema: type | None = None,
        requirements: ExtractionRequirements | CompositeExtractionRequirements | None = None,
    ) -> PipelineResult:
        """
        Execute the pipeline: transcribe then extract structured data.

        Args:
            file_path: Audio/video file to transcribe.
            user_requirements: Natural-language requirements describing desired fields.
            transcriber_ctor: Constructor args for Transcriber
                (e.g., enhanced_transcript, output_dir).
            transcribe_options: Call-time args for Transcriber.transcribe().
            extractor_ctor: Constructor args for DataExtractor (e.g., model override).
            extract_options: Call-time args for DataExtractor.extract().
            schema: Optional pre-generated schema model to reuse.
            requirements: Optional ExtractionRequirements corresponding to the schema.
        """
        transcriber_ctor = dict(transcriber_ctor or {})
        transcriber_ctor.setdefault("enhanced_transcript", False)
        transcriber_ctor.setdefault("api_config", self.transcription_config)
        transcriber = Transcriber(**transcriber_ctor)
        transcribe_options = transcribe_options or {}
        transcription = transcriber.transcribe(
            file_path=file_path,
            **transcribe_options,
        )

        extractor_ctor = dict(extractor_ctor or {})
        extractor_cfg = dict(extractor_ctor.pop("config", self.extraction_config))
        model_override = extractor_ctor.get("model")
        if model_override:
            extractor_cfg["model"] = model_override

        # Generate schema/requirements if not provided.
        if schema is None or requirements is None:
            schema_generator = SchemaGenerator(config=extractor_cfg)
            schema = schema_generator.generate_schema(user_requirements=user_requirements)
            requirements = schema_generator.item_requirements
        else:
            schema_generator = None

        documents: Sequence[str] = [
            transcription.enhanced_transcript or transcription.raw_transcript
        ]

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
            documents=documents,
            **extract_opts,
        )

        return PipelineResult(
            transcription=transcription,
            extracted_fields=extracted_fields,
            schema=schema,
            requirements=requirements,
        )

    # ------------------------------------------------------------------
    # Schema save/load helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_schema_dump(raw_dump: str) -> str:
        """Strip header/footer lines from print_pydantic_schema output."""
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
        """Persist schema and requirements to disk under schema_dir."""
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
        try:
            write_model_file(schema, schema_dir / f"{stem}_model.json")
        except SavedSchemaError as exc:
            # load_schema then rebuilds the model from the requirements file.
            print(f"Schema {schema.__name__!r} not saved as data: {exc}")

        payload = {
            "model_name": schema.__name__,
            "requirements": requirements.model_dump(),
        }
        req_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_schema(
        self, schema_dir: Path, schema_name: str
    ) -> tuple[type, ExtractionRequirements | CompositeExtractionRequirements] | None:
        """Load the saved model and requirements as data; None if they are missing.

        The saved model is rebuilt from ``<stem>_model.json``; ``<stem>.py`` is never
        imported. A folder with only the older files is rebuilt from the
        requirements where possible, else None (generate the schema again).
        """
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
        if schema is None:
            return None
        return schema, requirements
