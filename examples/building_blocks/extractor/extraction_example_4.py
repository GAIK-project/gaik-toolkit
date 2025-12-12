"""
Example 4: Persisting a dynamically generated schema for later reuse.

Steps demonstrated:
1. Use SchemaGenerator to create a schema and ExtractionRequirements from natural language.
2. Save the generated schema as real Python code plus the requirements as JSON.
3. Load the saved artifacts in a fresh context and run DataExtractor with them.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
import decimal
from decimal import Decimal
from typing import List, Literal, Optional

# Allow running the example without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.building_blocks.extractor import ExtractionRequirements  
from gaik.building_blocks.extractor import (DataExtractor, SchemaGenerator,  
                            get_openai_config)
from gaik.building_blocks.extractor.schema import print_pydantic_schema  

# ---------------------------------------------------------------------------
# Shared sample data (same as extraction_example_1.py)
# ---------------------------------------------------------------------------

USER_REQUIREMENTS = """
Extract project information from research grant documents.
For each project, extract:
- Project title (string)
- Project acronym (string)
- Lead institution (string)
- Total funding in EUR (number)
- Start date (date)
- Project status (enum: ongoing or completed)
"""

SAMPLE_DOCUMENTS = [
    """
    Project Report

    Title: Advanced AI Research Initiative
    Acronym: AIRI
    Lead Institution: University of Helsinki
    Total Funding: 2500000 euros
    Partners: Finland, Sweden, Norway, Denmark
    Status: Ongoing
    Start Date: 2024-01-15
    """,
    """
    Project Summary

    Project Name: Green Energy Solutions
    Short Name: GES
    Lead: Technical University of Munich
    Budget: 1800000 EUR
    Participating Countries: Germany, Austria, Switzerland
    Current Status: Completed
    Started: 2023-06-01
    """,
]

BASE_DIR = Path(__file__).parent
SCHEMA_PATH = BASE_DIR / "saved_project_schema.py"
REQUIREMENTS_PATH = BASE_DIR / "saved_project_requirements.json"


# ---------------------------------------------------------------------------
# Saving helpers
# ---------------------------------------------------------------------------


def _clean_schema_dump(raw_dump: str) -> str:
    """Strip header/footer lines from print_pydantic_schema output."""
    lines = raw_dump.splitlines()
    start_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("class "):
            start_idx = i
            break
    body = lines[start_idx:]
    # Remove trailing separator lines (e.g., ====) and blank lines
    while body and (set(body[-1].strip()) == {"="} or not body[-1].strip()):
        body.pop()
    return "\n".join(body).strip()


def save_schema_to_python(model: type, path: Path) -> None:
    """Dump the generated Pydantic model into a valid Python file."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        print_pydantic_schema(model, title="Saved Schema")

    schema_code = _clean_schema_dump(buffer.getvalue())
    template = f'''"""
Auto-generated schema module (do not edit manually).
"""

import decimal
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict

{schema_code}
'''
    path.write_text(template, encoding="utf-8")
    print(f"Schema saved to {path}")


def save_requirements(requirements: ExtractionRequirements, model_name: str, path: Path) -> None:
    payload = {
        "model_name": model_name,
        "requirements": requirements.model_dump(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Requirements saved to {path}")


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------


def load_saved_schema(path: Path, model_name: str):
    """Load the previously saved schema module and return the model class."""
    spec = importlib.util.spec_from_file_location("saved_project_schema", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    model_cls = getattr(module, model_name)
    return model_cls


def load_saved_requirements(path: Path) -> tuple[str, ExtractionRequirements]:
    data = json.loads(path.read_text(encoding="utf-8"))
    model_name = data["model_name"]
    requirements = ExtractionRequirements(**data["requirements"])
    return model_name, requirements


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def generate_and_persist_assets():
    """Generate schema + requirements, then write them to disk."""
    print("\n=== Generating schema and requirements ===")
    config = get_openai_config(use_azure=True)
    generator = SchemaGenerator(config=config)
    schema = generator.generate_schema(user_requirements=USER_REQUIREMENTS)

    save_schema_to_python(schema, SCHEMA_PATH)
    save_requirements(generator.item_requirements, schema.__name__, REQUIREMENTS_PATH)


def load_assets_and_extract():
    """Reload the saved schema + requirements and run extraction."""
    print("\n=== Loading saved schema and requirements ===")
    model_name, requirements = load_saved_requirements(REQUIREMENTS_PATH)
    SavedModel = load_saved_schema(SCHEMA_PATH, model_name)

    print("\n=== Running extraction with saved schema ===")
    config = get_openai_config(use_azure=True)
    extractor = DataExtractor(config=config)
    results = extractor.extract(
        extraction_model=SavedModel,
        requirements=requirements,
        user_requirements=USER_REQUIREMENTS,
        documents=SAMPLE_DOCUMENTS,
        save_json=True,
        json_path="extraction_results_saved_schema.json",
    )

    print("\nExtraction output:")
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    generate_and_persist_assets()
    load_assets_and_extract()


