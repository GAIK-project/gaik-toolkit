"""
VisionExtractor example — single-pass PDF/image → structured data.

Two test cases using documents in C:/Users/h02317/Downloads/temp/:

  Case 1 — Single document (singple_PO.pdf):
    One PDF containing both PO and BOM information.

  Case 2 — Multi-document (PO folder):
    PO.pdf + BOM1.pdf + BOM2.pdf + BOM3.pdf sent in a single LLM call.
    The model reads all four documents together and aligns PO items with
    the matching BOM via Material Number.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.vision_extractor import VisionExtractor

# ---------------------------------------------------------------------------
# Task descriptions
# ---------------------------------------------------------------------------

# extraction task involving a single document
TASK_SINGLE = Path("task_single_doc.txt").read_text(
    encoding="utf-8"
)

# extraction task involving multiple documents
TASK_MULTI = Path("task_multi_doc.txt").read_text(
    encoding="utf-8"
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# filename of the single document
SINGLE_PDF = Path("./single_PO.pdf")

# path of the folder containing multipele documents
PO_FOLDER = Path("PO")
MULTI_FILES = [
    PO_FOLDER / "PO.pdf",
    PO_FOLDER / "BOM1.pdf",
    PO_FOLDER / "BOM2.pdf",
    PO_FOLDER / "BOM3.pdf",
]

# path for single document schema
SCHEMA_DIR_SINGLE = Path(__file__).parent / "schema_single_PO"

# path for multiple document schema
SCHEMA_DIR_MULTI = Path(__file__).parent / "schema_multi"


def run_case(label: str, file_paths: list[Path], task: str, schema_dir: Path) -> None:
    print("\n" + "=" * 80)
    print(f"TEST CASE: {label}")
    print("=" * 80)

    t_start = time.perf_counter()
    extractor = VisionExtractor(
        # --- Provider selection ---
        model_provider="openai",       # "openai" | "claude" | "google"
        use_azure=True,                # True = Azure OpenAI, False = OpenAI direct
        vertex_ai=True,                # True = Google Vertex AI, False = Gemini direct (google only)

        # --- Model ---
        model="gpt-5.4",    # None = use model from config/.env; e.g., gemini-3.1-flash-lite
        api_config=None,               # None = auto-build from .env; or pass a config dict directly

        # --- Reasoning ---
        reasoning_effort="low",     # "low" | "medium" | "high"

        # --- Table handling ---
        merge_table=True,             # True = merge tables split across pages

        # --- Extra instructions ---
        additional_instructions=None,  # str appended to the user prompt, or None

        # --- Verification ---
        include_verification=False,    # True = add confidence_score + reasoning per field
    )
    result = extractor.extract(
        # --- Input files ---
        file_paths=file_paths,         # list of PDF or image paths (.pdf .png .jpg .jpeg .gif .webp .tiff .bmp)

        # --- Extraction task ---
        user_requirements=task,        # natural language description of what to extract

        # --- Schema (optional — generated automatically if omitted) ---
        extraction_model=None,         # pre-built Pydantic model class, or None
        requirements=None,             # pre-built ExtractionRequirements, or None
        schema_dir=schema_dir,         # directory to save/load schema.py + requirements.json
    )

    total_s = round(time.perf_counter() - t_start, 3)

    print(f"\nModel     : {result.model}")
    print(f"Files     : {result.documents_processed}")
    print(f"LLM time  : {result.duration_s}s")
    print(f"Total time: {total_s}s")
    if result.usage:
        print(f"Tokens    : {result.usage.total_tokens} total")
        print(f"Cost      : ${result.usage.cost_usd:.6f}")

    print("\nExtracted data:")
    print(json.dumps(result.data, indent=2, default=str, ensure_ascii=False))

    output_path = Path(__file__).parent / f"result_{label.lower().replace(' ', '_')}.json"
    output_path.write_text(
        json.dumps(result.data, indent=2, default=str, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    # Case 1: single PDF
    run_case("Single document", [SINGLE_PDF], TASK_SINGLE, SCHEMA_DIR_SINGLE)

    # Case 2: multi-document (PO + 3 BOMs in one call)
    # run_case("Multi document", MULTI_FILES, TASK_MULTI, SCHEMA_DIR_MULTI)
