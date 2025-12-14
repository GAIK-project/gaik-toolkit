"""
Reusable software component to transcribe audio and extract structured data.
Built on Gaik's transcriber and extractor components
Takes any audio, transcribes, parses fields and dynamically builds schema, extracts required fields.
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
from gaik.building_blocks.transcriber import Transcriber, TranscriptionResult
from gaik.building_blocks.extractor.schema import print_pydantic_schema


@dataclass
class PipelineResult:
    """Container for combined pipeline outputs."""

    transcription: TranscriptionResult      # Raw and enhanced transcript
    extracted_fields: list[dict[str, Any]]  # Structured data extracted
    schema: type                            # The generated Pydantic schema
    requirements: ExtractionRequirements    # Extraction requirements


class AudioToStructuredData:
    """End-to-end workflow: audio -> transcript -> structured extraction."""

    def __init__(
        self,
        *,
        api_config: dict | None = None,
        use_azure: bool = True,
    ) -> None:
        """
        Initialize the pipeline.

        Args:
            api_config: OpenAI/Azure config. If None, built via get_openai_config(use_azure).
            use_azure: Whether to build default config for Azure (ignored if api_config supplied).
        """
        self.api_config = api_config or get_openai_config(use_azure=use_azure)

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
        requirements: ExtractionRequirements | None = None,
    ) -> PipelineResult:
        """
        Execute the pipeline: transcribe then extract structured data.

        Args:
            file_path: Audio/video file to transcribe.
            user_requirements: Natural-language requirements describing desired fields.
            transcriber_ctor: Constructor args for Transcriber (e.g., enhanced_transcript, output_dir).
            transcribe_options: Call-time args for Transcriber.transcribe().
            extractor_ctor: Constructor args for DataExtractor (e.g., model override).
            extract_options: Call-time args for DataExtractor.extract().
            schema: Optional pre-generated schema model to reuse.
            requirements: Optional ExtractionRequirements corresponding to the schema.
        """
        transcriber = Transcriber(api_config=self.api_config, **(transcriber_ctor or {}))
        transcribe_options = transcribe_options or {}
        transcription = transcriber.transcribe(
            file_path=file_path,
            **transcribe_options,
        )

        extractor_cfg = self.api_config.copy()
        model_override = (extractor_ctor or {}).get("model")
        if model_override:
            extractor_cfg["model"] = model_override

        # Generate schema/requirements if not provided.
        if schema is None or requirements is None:
            schema_generator = SchemaGenerator(config=extractor_cfg)
            schema = schema_generator.generate_schema(user_requirements=user_requirements)
            requirements = schema_generator.item_requirements
        else:
            schema_generator = None

        documents: Sequence[str] = [transcription.enhanced_transcript or transcription.raw_transcript]

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
        """Load schema + requirements if both files exist; otherwise return None."""
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
