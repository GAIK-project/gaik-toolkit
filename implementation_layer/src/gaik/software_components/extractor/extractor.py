"""
Data Extractor for extracting structured data from documents using generated Pydantic schemas.

This module provides the DataExtractor class for extracting data from documents
using pre-generated Pydantic models.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import BaseModel

from gaik.observability import (
    UsageRecord,
    build_usage_record,
    measure_duration,
    openai_usage_to_dict,
)
from gaik.software_components.llm.factory import build_compat_client

from .schema import (
    SYSTEM_PARSER,
    ExtractionRequirements,
    _parse_with,
    apply_field_policies,
    normalize_extracted_data,
)


@dataclass
class ExtractionResult:
    """Structured return value from :meth:`DataExtractor.extract_with_usage`.

    Attributes:
        data: Extracted records, one per input document. Same shape as the
            list returned by :meth:`DataExtractor.extract`.
        usage: Aggregated token usage across all per-document calls.
            ``None`` when the LLM response did not carry a usage payload.
        duration_s: Wall-clock seconds spent in the extraction loop
            (does not include schema generation).
        model: Resolved model identifier the calls used.
        documents_processed: Convenience mirror of ``len(data)``.
    """

    data: list[dict] = field(default_factory=list)
    usage: UsageRecord | None = None
    duration_s: float = 0.0
    model: str = ""
    documents_processed: int = 0


def save_to_json(results: list[dict], json_path: str) -> None:
    """
    Save extraction results to JSON file.

    Args:
        results: List of extraction results (dicts)
        json_path: Output JSON file path
    """
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"OK Results saved to: {json_path}")


class DataExtractor:
    """
    Extractor for structured data from documents using Pydantic schemas.

    Takes a pre-generated Pydantic model and extracts data from documents
    according to that schema.

    Features:
    - Type-safe extraction with Pydantic validation
    - Data normalization (dates, lists, decimals)
    - Support for Azure OpenAI and OpenAI
    - Optional JSON export

    Usage:
        # Create config once
        config = get_openai_config(use_azure=True)  # or use_azure=False for standard OpenAI

        # Create extractor with config
        extractor = DataExtractor(config=config)

        # Extract data with pre-generated schema
        results = extractor.extract(
            extraction_model=MyPydanticModel,
            requirements=requirements,
            user_requirements="Extract...",
            documents=["doc1", "doc2"]
        )

        # Or extract and save to JSON
        results = extractor.extract(
            extraction_model=MyPydanticModel,
            requirements=requirements,
            user_requirements="Extract...",
            documents=["doc1", "doc2"],
            save_json=True,
            json_path="output.json"
        )
    """

    def __init__(self, config: dict, model: str | None = None):
        """
        Initialize the DataExtractor.

        Args:
            config: OpenAI configuration dict from get_openai_config()
            model: Optional model name override
        """
        self.config = config
        self.model = model if model else self.config["model"]
        self.client = build_compat_client(self.config)

    def _extract_one(
        self,
        doc: str,
        extraction_model: type[BaseModel],
        requirements: ExtractionRequirements,
        user_requirements: str,
    ) -> tuple[dict, UsageRecord | None]:
        """Run extraction on a single document.

        Returns the normalized record dict and a UsageRecord describing the
        LLM call's token / latency / cost — or ``None`` when the response
        carried no usage payload.
        """
        messages = [
            {"role": "system", "content": SYSTEM_PARSER},
            {
                "role": "user",
                "content": (
                    f"EXTRACTION TASK:\n{user_requirements}\n\nDocument:\n```txt\n{doc}\n```"
                ),
            },
        ]

        with measure_duration() as elapsed:
            resp = _parse_with(
                client=self.client,
                model=self.model,
                messages=messages,
                response_format=extraction_model,
            )
        duration_s = elapsed()

        usage_dict = openai_usage_to_dict(resp)
        usage = (
            build_usage_record("openai", self.model, usage_dict, duration_s)
            if usage_dict["total_tokens"] > 0
            else None
        )

        parsed = resp.choices[0].message.parsed
        result_dict = parsed.model_dump()

        # Apply field policies (fix nulls, missing keys, out-of-enum values)
        if isinstance(result_dict, dict):
            has_nested = False
            for key, value in list(result_dict.items()):
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    has_nested = True
                    result_dict[key] = [apply_field_policies(item, requirements) for item in value]
            if not has_nested:
                result_dict = apply_field_policies(result_dict, requirements)

        # Normalize extracted data (dates, lists, etc.)
        if isinstance(result_dict, dict):
            for key, value in list(result_dict.items()):
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    result_dict[key] = [
                        normalize_extracted_data(item, requirements) for item in value
                    ]
            result_dict = normalize_extracted_data(result_dict, requirements)

        return result_dict, usage

    def extract(
        self,
        extraction_model: type[BaseModel],
        requirements: ExtractionRequirements,
        user_requirements: str,
        documents: list[str],
        save_json: bool = False,
        json_path: str = "extraction_results.json",
    ) -> list[dict]:
        """
        Extract structured data from documents using a pre-generated Pydantic model.

        Args:
            extraction_model: Pre-generated Pydantic model class
            requirements: ExtractionRequirements with field specifications
            user_requirements: Original natural language requirements (for context)
            documents: List of document texts to extract from
            save_json: If True, save results to JSON file
            json_path: Output JSON file path (used if save_json=True)

        Returns:
            List of extraction results (dicts).

        See also:
            :meth:`extract_with_usage` returns the same data alongside
            aggregated token usage, latency, and cost.
        """
        print("\n" + "=" * 80)
        print("EXTRACTION PHASE")
        print("=" * 80)
        results: list[dict] = []

        for i, doc in enumerate(documents, start=1):
            print(f"\nProcessing document {i}/{len(documents)}...")
            result_dict, usage = self._extract_one(
                doc=doc,
                extraction_model=extraction_model,
                requirements=requirements,
                user_requirements=user_requirements,
            )
            if usage is not None:
                print(f"  [extraction] tokens={usage.total_tokens}")
            results.append(result_dict)

        print(f"\nOK Completed extraction from {len(documents)} document(s)")

        if save_json:
            save_to_json(results, json_path)

        return results

    def extract_with_usage(
        self,
        extraction_model: type[BaseModel],
        requirements: ExtractionRequirements,
        user_requirements: str,
        documents: list[str],
        save_json: bool = False,
        json_path: str = "extraction_results.json",
    ) -> ExtractionResult:
        """
        Extract structured data and report token usage + latency + cost.

        Same parameters as :meth:`extract`. Returns an
        :class:`ExtractionResult` whose ``data`` attribute holds the same
        list a plain ``extract()`` call would return; ``usage`` aggregates
        token counts across every per-document call (``None`` when the
        response objects carried no usage payload), ``duration_s`` is the
        wall-clock seconds for the extraction loop, ``model`` is the
        resolved model identifier, and ``documents_processed`` mirrors
        ``len(data)``.
        """
        print("\n" + "=" * 80)
        print("EXTRACTION PHASE")
        print("=" * 80)
        results: list[dict] = []
        aggregated: UsageRecord | None = None

        with measure_duration() as elapsed_total:
            for i, doc in enumerate(documents, start=1):
                print(f"\nProcessing document {i}/{len(documents)}...")
                result_dict, usage = self._extract_one(
                    doc=doc,
                    extraction_model=extraction_model,
                    requirements=requirements,
                    user_requirements=user_requirements,
                )
                if usage is not None:
                    print(f"  [extraction] tokens={usage.total_tokens}")
                    aggregated = usage if aggregated is None else aggregated + usage
                results.append(result_dict)
        total_duration_s = round(elapsed_total(), 3)

        print(f"\nOK Completed extraction from {len(documents)} document(s)")

        if save_json:
            save_to_json(results, json_path)

        return ExtractionResult(
            data=results,
            usage=aggregated,
            duration_s=total_duration_s,
            model=self.model,
            documents_processed=len(results),
        )
