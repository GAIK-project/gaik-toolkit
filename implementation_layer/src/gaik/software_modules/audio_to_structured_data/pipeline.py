"""
Reusable software component to transcribe audio and extract structured data.
Built on Gaik's transcriber and extractor components
Takes any audio, transcribes, parses fields and dynamically builds schema, extracts required fields.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterable, Sequence
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gaik.software_components.config import get_openai_config
from gaik.software_components.extractor import (
    CompositeExtractionRequirements,
    DataExtractor,
    ExtractionRequirements,
    SchemaGenerator,
    save_to_json,
)
from gaik.software_components.extractor.saved_schema import (
    load_saved_model,
    save_model_file,
)
from gaik.software_components.extractor.schema import (
    _holds_items,
    _resolve_fallback,
    print_pydantic_schema,
)
from gaik.software_components.llm.retries import is_transient_error
from gaik.software_components.transcriber import Transcriber, TranscriptionResult
from gaik.software_modules._options import EXTRACT_SET_BY_MODULE, checked_options

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Container for combined pipeline outputs."""

    transcription: TranscriptionResult  # Raw and enhanced transcript
    extracted_fields: list[dict[str, Any]]  # Structured data extracted
    schema: type  # The generated Pydantic schema
    requirements: ExtractionRequirements | CompositeExtractionRequirements
    # How many times the audio was transcribed (failed retries included), and
    # the fields named in ``retry_when_empty`` still empty in the result returned.
    transcription_attempts: int = 1
    empty_fields: list[str] = field(default_factory=list)


def _is_empty(value: Any, spec: Any) -> bool:
    """True when ``value`` is what the extractor writes for a value it did not find.

    The extractor's field policies replace a missing non-nullable value with the
    field's fallback: its explicit default, ``""`` for text and dates, or ``[]``
    for lists.
    """
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    return value == _resolve_fallback(spec)


def _watched_specs(requirements: Any, names: Sequence[str]) -> list[Any]:
    """The field specs for ``names``, in that order.

    For a parent with child collections the names refer to the parent's own
    fields. Raises :class:`ValueError` naming any field the schema lacks.
    """
    if isinstance(requirements, CompositeExtractionRequirements):
        requirements = requirements.parent_requirements
    by_name = {f.field_name: f for f in getattr(requirements, "fields", None) or []}
    unknown = [n for n in names if n not in by_name]
    if unknown:
        raise ValueError(
            f"retry_when_empty names fields the schema does not have: {unknown}; "
            f"its fields are {sorted(by_name)}"
        )
    return [by_name[n] for n in names]


def _item_lists(record: dict[str, Any], requirements: Any) -> list[list[Any]]:
    """The item lists of a nested-list schema's record; empty for a flat record.

    A nested-list schema's record is ``{"<container>": [item, ...]}`` with the
    named fields inside the items. A parent with child collections keeps its
    own fields on the record, so its child lists are not read as items.
    """
    if isinstance(requirements, CompositeExtractionRequirements):
        return []
    return [
        value for key, value in record.items() if _holds_items(key, value, requirements, record)
    ]


def _empty_fields(
    extracted: Sequence[Any], specs: Sequence[Any], requirements: Any = None
) -> list[str]:
    """Names of the fields in ``specs`` left empty in the extracted result.

    A flat record counts a field as empty when it is empty in any record. For
    a nested-list schema the fields live in the items: a field counts as empty
    when no item has a value for it, which is what a dropped passage of the
    audio leaves (an item that legitimately lacks a value is not a reason to
    transcribe again). No records, or no items, leaves every field empty.
    """
    records = [r for r in extracted or [] if isinstance(r, dict)]
    if not records:
        return [s.field_name for s in specs]
    empty: list[str] = []
    for spec in specs:
        for record in records:
            lists = _item_lists(record, requirements) if requirements is not None else []
            if lists:
                items = [i for values in lists for i in values if isinstance(i, dict)]
                if all(_is_empty(i.get(spec.field_name), spec) for i in items):
                    empty.append(spec.field_name)
                    break
            elif _is_empty(record.get(spec.field_name), spec):
                empty.append(spec.field_name)
                break
    return empty


def _checked_retry_options(retry_when_empty: Any, transcription_retries: Any) -> list[str]:
    if isinstance(transcription_retries, bool) or not isinstance(transcription_retries, int):
        raise ValueError("transcription_retries must be a whole number of 0 or more")
    if transcription_retries < 0:
        raise ValueError("transcription_retries must be a whole number of 0 or more")
    if retry_when_empty is None:
        return []
    # A list first: a generator would be used up by the check below, and a
    # value that is no collection at all is the same mistake as a bad name.
    if isinstance(retry_when_empty, (str, bytes)) or not isinstance(retry_when_empty, Iterable):
        raise ValueError("retry_when_empty must be a list of field names")
    names = list(retry_when_empty)
    if not all(isinstance(n, str) and n for n in names):
        raise ValueError("retry_when_empty must be a list of field names")
    return list(dict.fromkeys(names))


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
        retry_when_empty: Sequence[str] | None = None,
        transcription_retries: int = 2,
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
            retry_when_empty: Names of fields that the audio is expected to
                state, such as a reporter's name or an asset ID. When one of
                them comes back empty, the same audio is transcribed and
                extracted again with the same schema. Azure transcription
                sometimes leaves out speech, such as the opening sentences, in
                a random call, and a retry of the same audio usually recovers
                it. Nullable fields may be named. For a nested-list schema the
                names are the items' fields, and a field counts as empty when
                no item has it. ``None`` (the default) never retries. A name the
                schema lacks raises :class:`ValueError` before the audio is
                transcribed; a schema to generate is generated first, so its
                names are checked then.
            transcription_retries: The most retries to make for
                ``retry_when_empty`` (default 2). The run with the fewest empty
                named fields is returned, the earliest on a tie. A retry that
                fails on a rate limit, a timeout or a server error uses up that
                try and the next one is made; any other error ends the retries.
                Either way the best result so far is returned.

        Every option name must be a parameter of the component it goes to.
        Stage configs (``config``, ``api_config``) come from the constructor
        and are refused here; a :class:`ValueError` is raised before anything
        is transcribed.
        """
        transcriber_ctor = checked_options(transcriber_ctor, Transcriber, what="transcriber_ctor")
        transcribe_options = checked_options(
            transcribe_options,
            getattr(Transcriber, "transcribe", None),
            what="transcribe_options",
            set_by_module=("file_path",),
        )
        extractor_ctor = checked_options(extractor_ctor, DataExtractor, what="extractor_ctor")
        extract_options = checked_options(
            extract_options,
            getattr(DataExtractor, "extract", None),
            what="extract_options",
            set_by_module=EXTRACT_SET_BY_MODULE,
        )
        watched = _checked_retry_options(retry_when_empty, transcription_retries)

        extractor_cfg = dict(self.extraction_config)
        model_override = extractor_ctor.get("model")
        if model_override:
            extractor_cfg["model"] = model_override

        # Generate schema/requirements if not provided. With retry_when_empty
        # this runs before the audio is transcribed: it needs only the user's
        # requirements, and the names are then checked against the generated
        # fields before any transcription is paid for or lost. Without it the
        # order stays as it was, so a failed transcription costs no schema call.
        schema_generator = None
        if watched and (schema is None or requirements is None):
            schema_generator = SchemaGenerator(config=extractor_cfg)
            schema = schema_generator.generate_schema(user_requirements=user_requirements)
            requirements = schema_generator.item_requirements
        specs = _watched_specs(requirements, watched) if watched else []

        transcriber_ctor.setdefault("enhanced_transcript", False)
        transcriber = Transcriber(api_config=self.transcription_config, **transcriber_ctor)
        transcription = transcriber.transcribe(
            file_path=file_path,
            **transcribe_options,
        )

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
        # Each attempt extracts without writing; the result returned is written
        # once below, so the file and the return value are the same attempt.
        save_json = bool(extract_opts.pop("save_json", False))
        json_path = extract_opts.pop("json_path", "extraction_results.json")

        def extract_from(result: TranscriptionResult) -> list[dict[str, Any]]:
            documents: Sequence[str] = [result.enhanced_transcript or result.raw_transcript]
            return data_extractor.extract(
                extraction_model=schema,
                requirements=requirements,
                user_requirements=user_requirements,
                documents=documents,
                save_json=False,
                **extract_opts,
            )

        extracted_fields = extract_from(transcription)
        missing = _empty_fields(extracted_fields, specs, requirements)
        attempts = 1
        while missing and attempts <= transcription_retries:
            attempts += 1
            try:
                retry = transcriber.transcribe(file_path=file_path, **transcribe_options)
                retry_fields = extract_from(retry)
            except Exception as exc:
                # The best result so far stands. A transient error uses up this
                # try only; any other would come back on every try.
                if is_transient_error(exc):
                    logger.warning(
                        "retry %d of the transcription failed (%s); trying again",
                        attempts - 1,
                        type(exc).__name__,
                    )
                    continue
                logger.warning(
                    "retry %d of the transcription failed (%s); keeping the best result so far",
                    attempts - 1,
                    type(exc).__name__,
                )
                break
            retry_missing = _empty_fields(retry_fields, specs, requirements)
            if len(retry_missing) < len(missing):
                transcription, extracted_fields, missing = retry, retry_fields, retry_missing

        if save_json:
            save_to_json(extracted_fields, json_path)

        return PipelineResult(
            transcription=transcription,
            extracted_fields=extracted_fields,
            schema=schema,
            requirements=requirements,
            transcription_attempts=attempts,
            empty_fields=missing,
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
        """Load the saved model and requirements as data; None if they are missing.

        The saved model is rebuilt from ``<stem>_model.json``; ``<stem>.py`` is never
        imported. A folder with only the older files is rebuilt from the
        requirements where they determine the model; otherwise SavedSchemaError
        names the folder and how to convert it, and nothing is generated over it.
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
        return schema, requirements
