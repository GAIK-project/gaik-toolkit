"""
VisionExtractor example 
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.vision_extractor import VisionExtractor

# ---------------------------------------------------------------------------
# Task description
# ---------------------------------------------------------------------------

task = """
Extract purchase order data from the document.

Top-level fields:
- Purchase order number
- Delivery date (format: DD/MM/YYYY)
- Delivery address (Format: company name, street, postal code, city, country)
- Vendor number

For each line item, extract:
- Item number (e.g. 0100, 0200)
- Article code (internal supplier code)
- Dimensions (cross-section as stated, e.g. "25x8mm")
- Product form (Choose from: Flat, round, or rectangular bar)
- Material grade (e.g. "6061 Aluminum", "316 Stainless", "C260 Brass")
- Standard designation (alloy/standard code, e.g. "CW024A", "ASTM B221")
- Cut length (text string including the unit, e.g. "2000mm")
- Temper or condition (e.g. "Cold drawn, bright finish", "T6")
- Hardness HV (numeric, if stated, else null)
- Min bend radius (numeric, if stated, else null)
- Delivery length note (e.g. "in lengths of 3000mm", if stated, else null)
- Applicable standard (e.g. "ASTM B221", "EN 755-2", if stated, else null)
- Special flags (any remaining codes, e.g. "XK", "chamfered edges", else null)
- Quantity (text string including the unit, e.g. "8.600 kg")
"""


t_start = time.perf_counter()
extractor = VisionExtractor(
    # --- Provider selection ---
    model_provider="openai",       # "openai" | "claude" | "google"
    use_azure=True,                # True = Azure OpenAI, False = OpenAI direct
    vertex_ai=False,                # True = Google Vertex AI, False = Gemini direct (google only)

    # --- Model ---
    model="gpt-5.4-mini",    # None = use model from config/.env; e.g., gemini-3.1-flash-lite
    api_config=None,               # None = auto-build from .env; or pass a config dict directly

    # --- Reasoning ---
    reasoning_effort="low",     # "low" | "medium" | "high"

    # --- Table handling ---
    merge_table=True,             # True = merge tables split across pages

    # --- Extra instructions ---
    additional_instructions=None,  # str appended to the user prompt, or None

    # --- Verification ---
    include_verification=True,    # True = add confidence_score + reasoning per field
)
result = extractor.extract(
    # --- Input files ---
    file_paths=["./PO.pdf"],        # list of PDF or image paths (.pdf .png .jpg .jpeg .gif .webp .tiff .bmp)

    # --- Extraction task ---
    user_requirements=task,        # natural language description of what to extract

    schema_dir="example_schema",         # directory to save/load schema.py + requirements.json
)

total_s = round(time.perf_counter() - t_start, 3)

print(f"\nModel     : {result.model}")
print(f"Files     : {result.documents_processed}")
print(f"LLM time  : {result.duration_s}s")
if result.usage:
    print(f"Tokens    : {result.usage.total_tokens} total")
    print(f"Cost      : ${result.usage.cost_usd:.6f}")

print("\nExtracted data:")
print(json.dumps(result.data, indent=2, default=str, ensure_ascii=False))

output_path = Path(__file__).parent / "result_minimal.json"
output_path.write_text(
    json.dumps(result.data, indent=2, default=str, ensure_ascii=False), encoding="utf-8"
)
print(f"\nSaved to {output_path}")

